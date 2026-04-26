"""
V16 - generalized signal/graph runner for LS20.

This keeps the v15 Level 3 proof intact and reuses its augmented-state model
for later levels.  The runner:
  1. solves Level 1 and Level 2 with the known bootstrap routes,
  2. plans each level >=3 from the parsed game source,
  3. executes the generated plan in the live ARC environment.

Default target is Level 4, i.e. "try the next level after the v15 result".
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import numpy as np

import v15_level3_signal_planner as core


OUTPUT_DIR = Path("v16_signal_runner_output")


@dataclass
class LevelRun:
    level: int
    planned_length: int
    plan: str
    success: bool
    solved_step: Optional[int]
    final_level_count: int
    reason: str = ""


def log_sink(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    def write(msg: str = "") -> None:
        text = str(msg)
        print(text)
        lines.append(text)
        sys.stdout.flush()

    def flush() -> None:
        (output_dir / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    return write, flush


def normalize_scorecard(raw):
    scorecard = raw
    for _ in range(4):
        if isinstance(scorecard, dict):
            return scorecard
        if isinstance(scorecard, (list, tuple)):
            return scorecard
        if hasattr(scorecard, "model_dump"):
            return scorecard.model_dump()
        if hasattr(scorecard, "dict"):
            return scorecard.dict()
        if isinstance(scorecard, (bytes, bytearray)):
            scorecard = scorecard.decode("utf-8", errors="replace")
        elif not isinstance(scorecard, str):
            scorecard = str(scorecard)
        try:
            parsed = json.loads(scorecard)
        except json.JSONDecodeError:
            return scorecard
        if parsed == scorecard:
            return parsed
        scorecard = parsed
    return scorecard


def scorecard_summary(scorecard) -> str:
    if not isinstance(scorecard, dict):
        return str(scorecard)

    envs = scorecard.get("environments") or []
    env = envs[0] if envs else {}
    runs = env.get("runs") or []
    latest = runs[-1] if runs else {}
    score = scorecard.get("score", env.get("score"))
    levels = scorecard.get("total_levels_completed", env.get("levels_completed"))
    total_levels = scorecard.get("total_levels", env.get("level_count"))
    actions = scorecard.get("total_actions", env.get("actions"))
    state = latest.get("state", "")
    return f"score={score} levels={levels}/{total_levels} actions={actions} state={state}".strip()


def write_scorecard_snapshot(arc, write, label: str, full: bool = False):
    try:
        scorecard = normalize_scorecard(arc.get_scorecard())
        write(f"{label}: {scorecard_summary(scorecard)}")
        if full:
            write("\nScorecard:")
            write(json.dumps(scorecard, indent=2, default=str))
        return scorecard, None
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        write(f"{label}: unavailable ({error})")
        return None, error


def warmup_for_level(level: int) -> List[str]:
    # Existing LS20 runs need two upward ticks before Level 3 planning starts.
    # Later levels start directly at the source-defined player position.
    return ["U", "U"] if level == 3 else []


def model_seed_for_level(level: int) -> int:
    return len(warmup_for_level(level))


def describe_model(level: int, model: core.LevelModel, write) -> None:
    write(f"\n=== Level {level} model ===")
    write(f"walkable={len(model.walkable)} start={model.start_cell} exit={model.exit_cell}")
    write(
        "state "
        f"shape {model.start_shape}->{model.goal_shape}, "
        f"color {model.color_order[model.start_color_idx]}->{model.color_order[model.goal_color_idx]}, "
        f"rot {model.rotations[model.start_rot_idx]}->{model.rotations[model.goal_rot_idx]}, "
        f"energy={model.step_counter}/-{model.step_decrement}"
    )
    if len(model.goals) > 1:
        goals = [
            f"{goal.cell}:s{goal.shape}/c{model.color_order[goal.color_idx]}/r{model.rotations[goal.rot_idx]}"
            for goal in model.goals
        ]
        write(f"goals={goals}")
    write(f"shape_triggers={sorted(model.shape_triggers)}")
    write(f"color_triggers={sorted(model.color_triggers)}")
    write(f"rotation_triggers={sorted(model.rotation_triggers)}")
    write(f"collectibles={sorted(model.collectibles)}")
    for effect in model.moving_effects:
        write(
            f"moving {effect.tag}:{effect.name}@({effect.start_x},{effect.start_y}) "
            f"mask={effect.mask_name}@({effect.mask_x},{effect.mask_y})"
        )
    for pusher in model.pushers:
        write(
            f"pusher {pusher.name}@({pusher.x},{pusher.y}) "
            f"action={pusher.action} delta={pusher.delta} contacts={list(pusher.contacts)}"
        )


def log_trace(model: core.LevelModel, trace, write) -> None:
    for step, action, state, event in trace:
        pos, shape, color, rot, energy, _, completed_goals, movers = state
        label = event or ""
        tags = core.effect_tags_at(model, pos, movers)
        if "ttfwljgohq" in tags:
            label = (label + " shape").strip()
        if "soyhouuebz" in tags:
            label = (label + " color").strip()
        if "rhsxkxzdjz" in tags:
            label = (label + " rotation").strip()
        if label:
            write(
                f"  [{step:02d}] {action} -> {pos} "
                f"s={shape} c={model.color_order[color]} r={model.rotations[rot]} "
                f"energy={energy} goals={len(completed_goals)}/{len(model.goals)} {label}"
            )


def step_chars(env, actions: Sequence[str], write, prefix: str = "warmup"):
    act = core.action_map()
    result = None
    for i, action in enumerate(actions, 1):
        result = env.step(act[action])
        if not result.frame:
            write(f"{prefix} [{i}] {action} LIFE LOST")
            return result
        frame = np.array(result.frame[0])
        write(f"{prefix} [{i}] {action} pos={core.detect_player(frame)} lvl={int(result.levels_completed)}")
    return result


def execute_level(env, level: int, plan: Sequence[str], write) -> Tuple[bool, Optional[int], int, str]:
    act = core.action_map()
    target_completed = level
    current_completed = level - 1
    result = None
    for i, action in enumerate(plan, 1):
        result = env.step(act[action])
        if not result.frame:
            write(f"  [{i:02d}] {action} LIFE LOST")
            return False, None, int(getattr(result, "levels_completed", current_completed)), "life lost"
        frame = np.array(result.frame[0])
        lvl = int(result.levels_completed)
        write(f"  [{i:02d}] {action} pos={core.detect_player(frame)} lvl={lvl}")
        if lvl >= target_completed:
            write(f"*** LEVEL {level} SOLVED at planned step {i} ***")
            return True, i, lvl, ""
        current_completed = lvl
    final_level = int(getattr(result, "levels_completed", current_completed)) if result is not None else current_completed
    return final_level >= target_completed, None, final_level, "plan ended before completion"


def plan_level(level: int, write):
    model = core.build_model(level_number=level, seed_moves=model_seed_for_level(level))
    plan, trace = core.find_plan(model)
    describe_model(level, model, write)
    write(f"Plan L{level} ({len(plan)} moves): {''.join(plan)}")
    log_trace(model, trace, write)
    return model, plan, trace


def run(target_level: int) -> Dict[str, object]:
    requested_target_level = target_level
    max_level = core.max_level_number()
    effective_target_level = min(target_level, max_level)
    output_dir = OUTPUT_DIR / f"target_L{requested_target_level}"
    write, flush = log_sink(output_dir)
    runs: List[LevelRun] = []
    try:
        arc_module, game_action = core.ensure_arc_runtime()
        arc = arc_module.Arcade()
        env = arc.make(core.GAME_ID, render_mode=None)

        if target_level > max_level:
            write(
                f"Requested target Level {target_level}, but {core.GAME_ID} "
                f"source defines only {max_level} levels. Solving through Level {max_level}."
            )
        if effective_target_level < 3:
            write(f"Target Level {effective_target_level} is handled by bootstrap only.")

        write("=== Bootstrap ===")
        result = core.do_l1(env)
        write(f"L1 lvl={result.levels_completed}")
        write_scorecard_snapshot(arc, write, "Score after L1")
        result = core.solve_l2(env)
        write(f"L2 lvl={result.levels_completed}")
        write_scorecard_snapshot(arc, write, "Score after L2")
        if int(result.levels_completed) < 2:
            raise RuntimeError("Level 2 bootstrap failed")

        for level in range(3, effective_target_level + 1):
            warmup = warmup_for_level(level)
            if warmup:
                write(f"\n=== Level {level} warmup ===")
                step_chars(env, warmup, write)

            try:
                _, plan, _ = plan_level(level, write)
            except Exception as exc:
                write(f"Planning failed for Level {level}: {type(exc).__name__}: {exc}")
                runs.append(LevelRun(level, 0, "", False, None, level - 1, str(exc)))
                break

            ok, solved_step, final_level, reason = execute_level(env, level, plan, write)
            if solved_step is not None and solved_step != len(plan):
                write(
                    f"Observed runtime solve-step {solved_step} differs from "
                    f"static plan length {len(plan)}."
                )
            runs.append(LevelRun(level, len(plan), "".join(plan), ok, solved_step, final_level, reason))
            if ok:
                write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not ok:
                break

        success = bool(
            (effective_target_level < 3 and int(result.levels_completed) >= effective_target_level)
            or (runs and runs[-1].level == effective_target_level and runs[-1].success)
        )
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = write_scorecard_snapshot(arc, write, "Final score", full=True)

        summary = {
            "requested_target_level": requested_target_level,
            "target_level": effective_target_level,
            "available_levels": max_level,
            "requested_target_exists": requested_target_level <= max_level,
            "success": success,
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
            "runs": [asdict(run) for run in runs],
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=4)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
