from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import numpy as np

from .perception import FrameDelta, Perception
from .trace import TraceLogger


@dataclass(frozen=True)
class ActionProbe:
    action_id: int
    before_hash: str
    after_hash: str
    after_frame: np.ndarray = field(repr=False, compare=False)
    delta: FrameDelta
    state: str
    levels_completed: int
    available_actions: List[int]


class ClickKernelModel:
    """Milestone 1 stub.

    Clicks are a major ARC operator class, but this milestone only records that
    click modeling is intentionally absent.  The interface is here so future
    probes can attach evidence without changing BlackBoxAgent orchestration.
    """

    def observe_probe(self, probe: ActionProbe) -> None:
        return None

    def propose_clicks(self) -> List[Dict[str, int]]:
        return []


class ProbeRunner:
    """Execute reset/action probes using only environment frames."""

    def __init__(
        self,
        game_id: str,
        *,
        perception: Perception,
        logger: TraceLogger,
        render_mode: Optional[str] = None,
    ) -> None:
        self.game_id = game_id
        self.perception = perception
        self.logger = logger
        self.render_mode = render_mode
        self.arc = None

    def make_env(self):
        import arc_agi

        if self.arc is None:
            self.arc = arc_agi.Arcade()
        return self.arc.make(self.game_id, render_mode=self.render_mode)

    def reset(self, env):
        result = env.reset()
        frame = self._first_frame(result)
        self.logger.event(
            "reset",
            game_id=str(getattr(result, "game_id", self.game_id)),
            state=str(getattr(result, "state", None)),
            levels_completed=int(getattr(result, "levels_completed", 0)),
            available_actions=self.available_actions(result),
            frame_hash=self.perception.hash_frame(frame),
        )
        return result, frame

    def step(self, env, action_id: int, before_frame: np.ndarray, data: Optional[Dict[str, int]] = None) -> ActionProbe:
        from arcengine import GameAction

        action = getattr(GameAction, f"ACTION{int(action_id)}")
        if data is None:
            result = env.step(action)
        else:
            result = env.step(action, data)
        after_frame = self._first_frame(result)
        before_hash = self.perception.hash_frame(before_frame)
        after_hash = self.perception.hash_frame(after_frame)
        delta = self.perception.diff(before_frame, after_frame)
        probe = ActionProbe(
            action_id=action_id,
            before_hash=before_hash,
            after_hash=after_hash,
            after_frame=after_frame,
            delta=delta,
            state=str(getattr(result, "state", None)),
            levels_completed=int(getattr(result, "levels_completed", 0)),
            available_actions=self.available_actions(result),
        )
        self.logger.event(
            "step",
            action_id=action_id,
            data=data or {},
            before_hash=before_hash,
            after_hash=after_hash,
            changed_count=delta.changed_count,
            impact=delta.impact,
            bbox=delta.bbox,
            added_centroid=delta.added_centroid,
            erased_centroid=delta.erased_centroid,
            motion_delta=delta.motion_delta,
            state=probe.state,
            levels_completed=probe.levels_completed,
        )
        return probe

    def one_step_action_probes(self, action_ids: Iterable[int]) -> List[ActionProbe]:
        probes: List[ActionProbe] = []
        for action_id in action_ids:
            env = self.make_env()
            _, before = self.reset(env)
            probe = self.step(env, int(action_id), before)
            probes.append(probe)
            self.logger.event(
                "initial_probe",
                action_id=int(action_id),
                changed_count=probe.delta.changed_count,
                impact=probe.delta.impact,
                motion_delta=probe.delta.motion_delta,
                state=probe.state,
            )
        return probes

    def repeated_action_probes(self, action_ids: Iterable[int], repeats: int = 4) -> Dict[int, List[ActionProbe]]:
        sequences: Dict[int, List[ActionProbe]] = {}
        for action_id in action_ids:
            env = self.make_env()
            _, before = self.reset(env)
            action_sequence: List[ActionProbe] = []
            for repeat_index in range(repeats):
                probe = self.step(env, int(action_id), before)
                action_sequence.append(probe)
                before = probe.after_frame
                self.logger.event(
                    "repeat_probe",
                    action_id=int(action_id),
                    repeat_index=repeat_index,
                    changed_count=probe.delta.changed_count,
                    centroid=probe.delta.centroid,
                    impact=probe.delta.impact,
                    state=probe.state,
                )
            sequences[int(action_id)] = action_sequence
        return sequences

    def available_actions(self, result) -> List[int]:
        raw_actions = list(getattr(result, "available_actions", []) or [])
        return [int(a) for a in raw_actions if 1 <= int(a) <= 4]

    def _first_frame(self, result) -> np.ndarray:
        frames = getattr(result, "frame", None)
        if not frames:
            raise RuntimeError("environment returned no frame")
        return np.asarray(frames[0], dtype=np.int16)
