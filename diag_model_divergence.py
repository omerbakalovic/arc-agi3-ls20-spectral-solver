"""Compare the signal planner's predicted state with the live LS20 runtime.

The planner is intentionally small and symbolic, so when a later level fails the
fastest way forward is to find the first exact transition where its state graph
stops matching the engine.  This script bootstraps through earlier levels, then
logs model-vs-runtime state after every planned move on the target level.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import numpy as np

import v15_level3_signal_planner as core
import v16_signal_runner as runner


OUTPUT_DIR = Path("diag_model_divergence_output")
COMPARE_KEYS = ("pos", "shape", "color_idx", "rot_idx")


@dataclass
class StepRecord:
    step: int
    action: str
    event: str
    expected: Dict[str, object]
    actual: Dict[str, object]
    mismatches: List[str]


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


def frame_pos(result) -> Optional[Tuple[int, int]]:
    if result is None or not result.frame:
        return None
    return core.detect_player(np.array(result.frame[0]))


def live_snapshot(env, result=None) -> Dict[str, object]:
    game = env._game
    color_idx = int(game.hiaauhahz)
    rot_idx = int(game.cklxociuu)
    logical_pos = (int(game.gudziatsk.y), int(game.gudziatsk.x))
    visible_pos = frame_pos(result)
    return {
        "pos": visible_pos or logical_pos,
        "logical_pos": logical_pos,
        "shape": int(game.fwckfzsyc),
        "color_idx": color_idx,
        "color": int(game.tnkekoeuk[color_idx]),
        "rot_idx": rot_idx,
        "rot": int(game.dhksvilbb[rot_idx]),
        "energy": int(game._step_counter_ui.current_steps),
        "level_index": int(game.level_index),
        "levels_completed": int(getattr(result, "levels_completed", game.level_index)),
        "match": bool(game.bejndxqqzf(0)),
    }


def predicted_snapshot(model: core.LevelModel, state: core.State) -> Dict[str, object]:
    pos, shape, color_idx, rot_idx, energy, collected, completed_goals, movers = state
    return {
        "pos": pos,
        "shape": shape,
        "color_idx": color_idx,
        "color": model.color_order[color_idx],
        "rot_idx": rot_idx,
        "rot": model.rotations[rot_idx],
        "energy": energy,
        "collected": sorted(collected),
        "completed_goals": sorted(completed_goals),
        "movers": [list(mover) for mover in movers],
        "match": len(completed_goals) == len(model.goals),
    }


def trigger_label(
    model: core.LevelModel,
    pos: Tuple[int, int],
    movers: Tuple[Tuple[int, int, int], ...],
) -> str:
    labels: List[str] = []
    tags = core.effect_tags_at(model, pos, movers)
    if "ttfwljgohq" in tags:
        labels.append("shape")
    if "soyhouuebz" in tags:
        labels.append("color")
    if "rhsxkxzdjz" in tags:
        labels.append("rotation")
    if pos in model.collectibles:
        labels.append("collectible")
    push = core.pusher_at(model, pos)
    if push is not None:
        labels.append(f"pusher:{push.name}")
    return "+".join(labels)


def fmt_state(state: Dict[str, object]) -> str:
    return (
        f"pos={state.get('pos')} "
        f"s={state.get('shape')} "
        f"c={state.get('color')}#{state.get('color_idx')} "
        f"r={state.get('rot')}#{state.get('rot_idx')} "
        f"e={state.get('energy')}"
    )


def bootstrap_to_level(env, level: int, write) -> None:
    write("=== Bootstrap ===")
    result = core.do_l1(env)
    write(f"L1 lvl={result.levels_completed}")
    result = core.solve_l2(env)
    write(f"L2 lvl={result.levels_completed}")
    if int(result.levels_completed) < 2:
        raise RuntimeError("Level 2 bootstrap failed")

    for prior in range(3, level):
        warmup = runner.warmup_for_level(prior)
        if warmup:
            runner.step_chars(env, warmup, write, prefix=f"L{prior} warmup")
        _, plan, _ = runner.plan_level(prior, write)
        ok, solved_step, final_level, reason = runner.execute_level(env, prior, plan, write)
        if not ok:
            raise RuntimeError(
                f"Could not reach Level {prior + 1}; L{prior} ended at "
                f"{final_level} ({reason or 'unsolved'})"
            )
        write(f"L{prior} reached next level at step {solved_step}")


def compare_level(env, level: int, write, stop_after_first: bool = False) -> Dict[str, object]:
    warmup = runner.warmup_for_level(level)
    if warmup:
        write(f"\n=== Level {level} warmup ===")
        runner.step_chars(env, warmup, write, prefix=f"L{level} warmup")

    model, plan, trace = runner.plan_level(level, write)
    actual_start = live_snapshot(env)
    write(f"\n=== Level {level} comparison ===")
    write(f"Runtime start: {fmt_state(actual_start)}")

    act = core.action_map()
    records: List[StepRecord] = []
    first_mismatch: Optional[StepRecord] = None
    solved_step: Optional[int] = None
    final_level = level - 1

    for (step, action, state, event) in trace:
        result = env.step(act[action])
        if not result.frame:
            actual = live_snapshot(env, result)
            expected = predicted_snapshot(model, state)
            record = StepRecord(
                step=step,
                action=action,
                event=event or trigger_label(model, expected["pos"], state[-1]),
                expected=expected,
                actual=actual,
                mismatches=["life_lost"],
            )
            records.append(record)
            first_mismatch = first_mismatch or record
            write(f"[{step:02d}] {action} LIFE LOST")
            break

        final_level = int(result.levels_completed)
        expected = predicted_snapshot(model, state)
        actual = live_snapshot(env, result)
        event_label = event or trigger_label(model, expected["pos"], state[-1])

        if final_level >= level:
            solved_step = step
            write(
                f"[{step:02d}] {action} runtime solved L{level}; "
                f"expected {fmt_state(expected)}"
            )
            break

        mismatches = [
            key for key in COMPARE_KEYS
            if expected.get(key) != actual.get(key)
        ]
        record = StepRecord(
            step=step,
            action=action,
            event=event_label,
            expected=expected,
            actual=actual,
            mismatches=mismatches,
        )
        records.append(record)

        suffix = ""
        if event_label:
            suffix += f" event={event_label}"
        if actual.get("logical_pos") != actual.get("pos"):
            suffix += f" logical_pos={actual.get('logical_pos')}"
        if mismatches:
            suffix += " MISMATCH=" + ",".join(mismatches)
            first_mismatch = first_mismatch or record
        write(
            f"[{step:02d}] {action} "
            f"expected {fmt_state(expected)} | actual {fmt_state(actual)}{suffix}"
        )
        if mismatches and stop_after_first:
            break

    return {
        "level": level,
        "plan": "".join(plan),
        "planned_length": len(plan),
        "solved_step": solved_step,
        "final_level": final_level,
        "first_mismatch": asdict(first_mismatch) if first_mismatch else None,
        "records": [asdict(record) for record in records],
    }


def run(level: int, stop_after_first: bool = False) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"level_{level}"
    write, flush = log_sink(output_dir)
    try:
        arc_module, _ = core.ensure_arc_runtime()
        arc = arc_module.Arcade()
        env = arc.make(core.GAME_ID, render_mode=None)
        bootstrap_to_level(env, level, write)
        summary = compare_level(env, level, write, stop_after_first=stop_after_first)
        first = summary["first_mismatch"]
        if first:
            write(
                "\nFIRST MISMATCH: "
                f"step {first['step']} action {first['action']} "
                f"keys={','.join(first['mismatches'])}"
            )
        else:
            write("\nFIRST MISMATCH: none")
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", type=int, default=5)
    parser.add_argument("--stop-after-first", action="store_true")
    args = parser.parse_args()
    run(args.level, stop_after_first=args.stop_after_first)


if __name__ == "__main__":
    main()
