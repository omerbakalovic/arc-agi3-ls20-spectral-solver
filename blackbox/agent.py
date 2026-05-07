from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .hazard import HazardModel
from .movement import MovementModel, MovementOutcome
from .perception import Component, Perception
from .planner import BFSPlanner, PartialGraph
from .probe import ClickKernelModel, ProbeRunner
from .trace import TraceLogger


class BlackBoxAgent:
    """Milestone 1 black-box agent.

    The agent sees frames and action deltas only.  It does not read level source,
    sprite tags, object IDs, or hand-authored LS20 coordinates.
    """

    def __init__(
        self,
        game_id: str = "ls20",
        *,
        output_root: Path | str = "blackbox_runs",
        max_steps: int = 260,
        attempts: int = 1,
        save_frames: bool = True,
    ) -> None:
        self.game_id = game_id
        self.max_steps = max_steps
        self.max_attempts = max(1, int(attempts))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_dir = Path(output_root) / f"{game_id}_{stamp}"
        self.logger = TraceLogger(self.output_dir, save_frames=save_frames)
        self.perception = Perception()
        self.probes = ProbeRunner(game_id, perception=self.perception, logger=self.logger)
        self.movement = MovementModel()
        self.hazards = HazardModel()
        self.clicks = ClickKernelModel()
        self.graph = PartialGraph()
        self.planner = BFSPlanner([])
        self.current_pos = (0, 0)
        self.levels_completed = 0
        self.step_count = 0
        self.attempt_summaries: List[Dict[str, object]] = []

    def run(self) -> Dict[str, object]:
        calibration_env = self.probes.make_env()
        reset_result, frame = self.probes.reset(calibration_env)
        self.logger.frame("calibration_reset", frame, level=self.levels_completed)

        action_ids = self.probes.available_actions(reset_result)
        self.planner.set_action_ids(action_ids)
        self.logger.event(
            "agent_start",
            game_id=self.game_id,
            action_ids=action_ids,
            max_steps_per_attempt=self.max_steps,
            attempts=self.max_attempts,
        )

        self._initial_probes(action_ids)
        self.movement.actor_center = None
        self.logger.event("live_actor_tracker_reset", reason="discard_probe_env_centroid")

        terminal_state: Optional[str] = None
        for attempt_index in range(1, self.max_attempts + 1):
            attempt_summary = self._run_attempt(attempt_index, action_ids)
            self.attempt_summaries.append(attempt_summary)
            terminal_state = str(attempt_summary["terminal_state"])
            if "WIN" in terminal_state or terminal_state in {"NO_FRONTIER", "MAX_STEPS"}:
                break

        scorecard = self._scorecard()
        summary: Dict[str, object] = {
            "game_id": self.game_id,
            "steps": self.step_count,
            "levels_completed": self.levels_completed,
            "terminal_state": terminal_state or "NOT_STARTED",
            "attempts": self.attempt_summaries,
            "hazards": self.hazards.to_dict(),
            "graph": self.graph.stats(),
            "action_vectors": {str(k): v for k, v in self.movement.action_vectors.items()},
            "pixel_step_estimate": self.movement.pixel_step_estimate,
            "output_dir": str(self.output_dir),
            "scorecard": scorecard,
        }
        self.logger.set_summary(**summary)
        self.logger.close()
        return summary

    def _run_attempt(self, attempt_index: int, action_ids: List[int]) -> Dict[str, object]:
        env = self.probes.make_env()
        reset_result, previous_frame = self.probes.reset(env)
        self.graph = PartialGraph()
        self.graph.load_forbidden(self.hazards.forbidden_edges(self.levels_completed))
        self.planner.set_action_ids(action_ids)
        self.planner.pending_path.clear()
        self.current_pos = (0, 0)
        self.movement.actor_center = None
        attempt_steps = 0
        terminal_state: Optional[str] = None

        self.logger.frame(f"attempt_{attempt_index}_reset", previous_frame, level=self.levels_completed)
        self.logger.event(
            "attempt_start",
            attempt=attempt_index,
            levels_completed=self.levels_completed,
            action_ids=action_ids,
            forbidden_edges=sorted([(*pos, action_id) for pos, action_id in self.graph.forbidden]),
        )

        while attempt_steps < self.max_steps:
            observation = self.perception.observe(previous_frame)
            target_estimates = self._target_estimates(observation)
            self.planner.set_targets(target_estimates)
            self.logger.event(
                "planner_context",
                attempt=attempt_index,
                step=self.step_count,
                attempt_step=attempt_steps,
                pos=self.current_pos,
                graph=self.graph.stats(),
                hazards=self.hazards.stats(),
                target_estimates=target_estimates,
                actor_center=self.movement.actor_center,
                pixel_step=self.movement.pixel_step_estimate,
            )

            action_id, reason = self.planner.next_action(self.graph, self.current_pos)
            if action_id is None:
                terminal_state = "NO_FRONTIER"
                self.logger.event(
                    "agent_stop",
                    attempt=attempt_index,
                    reason=reason,
                    pos=self.current_pos,
                    graph=self.graph.stats(),
                    hazards=self.hazards.stats(),
                )
                break

            probe = self.probes.step(env, action_id, previous_frame)
            outcome = self.movement.classify(action_id, probe.delta, self.current_pos)
            self._record_outcome(outcome)
            self.step_count += 1
            attempt_steps += 1
            previous_frame = probe.after_frame
            self.logger.frame(f"step_{self.step_count:04d}_a{action_id}", previous_frame, level=self.levels_completed)
            self.logger.event(
                "movement_outcome",
                attempt=attempt_index,
                step=self.step_count,
                attempt_step=attempt_steps,
                action_id=action_id,
                planner_reason=reason,
                outcome=outcome,
                graph=self.graph.stats(),
            )

            if probe.levels_completed > self.levels_completed:
                self.levels_completed = probe.levels_completed
                self.logger.event(
                    "level_completed",
                    levels_completed=self.levels_completed,
                    step=self.step_count,
                    state=probe.state,
                )
                self._reset_level_model()

            if "NOT_FINISHED" not in probe.state:
                terminal_state = str(probe.state)
                if "GAME_OVER" in terminal_state:
                    hazard_edge = self.hazards.record_terminal_edge(
                        level_index=self.levels_completed,
                        pos=outcome.current_pos,
                        action_id=action_id,
                        state=terminal_state,
                        step=self.step_count,
                    )
                    self.graph.record_forbidden(outcome.current_pos, action_id)
                    self.planner.pending_path.clear()
                    self.logger.event(
                        "hazard_edge",
                        attempt=attempt_index,
                        edge=hazard_edge,
                        hazards=self.hazards.to_dict(),
                    )
                self.logger.event(
                    "terminal_state",
                    attempt=attempt_index,
                    state=probe.state,
                    step=self.step_count,
                    attempt_step=attempt_steps,
                )
                break

        return {
            "attempt": attempt_index,
            "steps": attempt_steps,
            "levels_completed": self.levels_completed,
            "terminal_state": terminal_state or "MAX_STEPS",
            "graph": self.graph.stats(),
            "hazards": self.hazards.stats(),
        }

    def _initial_probes(self, action_ids: List[int]) -> List[MovementOutcome]:
        outcomes: List[MovementOutcome] = []
        repeat_sequences = self.probes.repeated_action_probes(action_ids, repeats=4)
        for action_id, sequence in repeat_sequences.items():
            outcome = self.movement.fit_action_from_centroid_sequence(
                action_id,
                [probe.delta for probe in sequence],
            )
            if outcome is not None:
                outcomes.append(outcome)
                self.logger.event("centroid_sequence_hypothesis", action_id=action_id, outcome=outcome)

        for outcome in self._infer_hash_reversals(action_ids):
            outcomes.append(outcome)
            self.logger.event("hash_reversal_hypothesis", action_id=outcome.action_id, outcome=outcome)

        for probe in self.probes.one_step_action_probes(action_ids):
            outcome = self.movement.classify(probe.action_id, probe.delta, (0, 0))
            outcomes.append(outcome)
            self.clicks.observe_probe(probe)
            self.logger.event("initial_movement_hypothesis", action_id=probe.action_id, outcome=outcome)
        return outcomes

    def _infer_hash_reversals(self, action_ids: List[int]) -> List[MovementOutcome]:
        inferred: List[MovementOutcome] = []
        for source_action_id in action_ids:
            if source_action_id not in self.movement.action_vectors:
                continue
            for candidate_action_id in action_ids:
                if candidate_action_id == source_action_id:
                    continue
                if candidate_action_id in self.movement.action_vectors:
                    continue
                env = self.probes.make_env()
                _, reset_frame = self.probes.reset(env)
                reset_hash = self.perception.hash_frame(reset_frame)
                first = self.probes.step(env, source_action_id, reset_frame)
                if first.after_hash == reset_hash:
                    continue
                second = self.probes.step(env, candidate_action_id, first.after_frame)
                if second.after_hash == reset_hash:
                    outcome = self.movement.set_reversal(candidate_action_id, source_action_id)
                    if outcome is not None:
                        inferred.append(outcome)
                    break
        return inferred

    def _record_outcome(self, outcome: MovementOutcome) -> None:
        if outcome.moved:
            self.graph.record_move(outcome.current_pos, outcome.action_id, outcome.next_pos)
            opposite_action = self.movement.opposite_action(outcome.action_id)
            if opposite_action is not None:
                self.graph.record_inferred_move(outcome.next_pos, opposite_action, outcome.current_pos)
            self.current_pos = outcome.next_pos
        elif outcome.blocked:
            self.graph.record_wall(outcome.current_pos, outcome.action_id)
            self.planner.pending_path.clear()
        else:
            self.graph.record_ambiguous(outcome.current_pos, outcome.action_id)
            self.planner.pending_path.clear()

    def _reset_level_model(self) -> None:
        self.graph = PartialGraph()
        self.graph.load_forbidden(self.hazards.forbidden_edges(self.levels_completed))
        self.planner.pending_path.clear()
        self.current_pos = (0, 0)
        self.movement.actor_center = None
        self.logger.event(
            "level_model_reset",
            levels_completed=self.levels_completed,
            forbidden_edges=sorted([(*pos, action_id) for pos, action_id in self.graph.forbidden]),
        )

    def _target_estimates(self, observation) -> List[tuple[int, int]]:
        targets: List[tuple[int, int]] = []
        for component in self._visible_target_candidates(observation):
            grid = self.movement.target_grid_estimate(self.current_pos, component.centroid)
            if grid is not None and grid != self.current_pos:
                targets.append(grid)
        return sorted(set(targets))

    def _visible_target_candidates(self, observation) -> List[Component]:
        exclude_values = set()
        if self.movement.actor_center is not None:
            ay, ax = self.movement.actor_center
            for component in observation.components:
                cy, cx = component.centroid
                if abs(cy - ay) <= 4 and abs(cx - ax) <= 4:
                    exclude_values.add(component.value)
        return observation.rare_components(min_size=2, max_size=80, max_count=10, exclude_values=exclude_values)

    def _scorecard(self) -> object:
        try:
            if self.probes.arc is None:
                return None
            return self.probes.arc.get_scorecard()
        except Exception as exc:
            return {"error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Milestone 1 black-box ARC agent")
    parser.add_argument("--game", default="ls20")
    parser.add_argument("--max-steps", type=int, default=260)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--output-root", default="blackbox_runs")
    parser.add_argument("--no-save-frames", action="store_true")
    args = parser.parse_args()

    agent = BlackBoxAgent(
        args.game,
        output_root=args.output_root,
        max_steps=args.max_steps,
        attempts=args.attempts,
        save_frames=not args.no_save_frames,
    )
    summary = agent.run()
    print("BLACKBOX SUMMARY")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
