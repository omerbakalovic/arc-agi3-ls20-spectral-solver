"""
V27 - click/particle merge solver checkpoint for ARC-AGI-3 SU15.

SU15 is a click-only merge puzzle.  Clicks select nearby numbered blocks and
particles; numbered blocks move to the click point and equal values merge into
the next value.  Level-1 particles act as persistent hazards because unselected
particles home toward blocks and decrement them on contact.

This checkpoint replays engine-verified plans for the first four levels.  The
first three levels are pure merge-and-place plans.  Level 4 introduces explicit
particle management: a particle is pushed away while the block merge ladder is
completed and moved into the target zone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "su15"
OUTPUT_DIR = Path("v27_su15_output")
Position = Tuple[int, int]


PLANS: Dict[int, List[Position]] = {
    1: [(4, 50), (8, 42), (12, 34), (16, 26), (20, 18), (28, 14), (36, 14), (44, 14)],
    2: [
        (16, 54), (48, 54), (24, 54), (32, 54), (40, 54), (16, 38),
        (40, 38), (24, 38), (32, 38), (36, 46), (32, 38), (32, 30),
    ],
    3: [
        (60, 22), (32, 18), (12, 26), (20, 18), (16, 22), (32, 26),
        (24, 22), (52, 22), (48, 26), (44, 34), (36, 38), (28, 42),
        (20, 46), (12, 50), (24, 30), (24, 38), (24, 46),
    ],
    4: [
        (32, 30), (32, 46), (32, 38), (48, 30), (8, 26), (8, 42),
        (8, 34), (24, 38), (16, 36), (12, 44), (8, 52), (8, 56),
    ],
}


@dataclass
class ClickStep:
    level: int
    step: int
    grid: Position
    data: Dict[str, int]


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Position]
    trace: List[ClickStep]
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


def click_data(position: Position) -> Dict[str, int]:
    return {"x": int(position[0]), "y": int(position[1])}


def snapshot(game) -> Dict[str, object]:
    return {
        "zmlx": [
            {
                "level": int(game.kqywaxhmsb[sprite]),
                "x": int(sprite.x),
                "y": int(sprite.y),
                "center": list(game.jdeyppambj(sprite)),
            }
            for sprite in game.lkujttxgs
        ],
        "particles": [
            {
                "level": int(game.dfqhmningy(game.kcuphgwar[sprite])),
                "x": int(sprite.x),
                "y": int(sprite.y),
                "center": list(game.jdeyppambj(sprite)),
            }
            for sprite in game.fezhhzhih
        ],
    }


def execute_level(env, game_action, plan: List[Position], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    trace: List[ClickStep] = []
    final_level_count = level - 1

    write(f"plan_len={len(plan)} clicks={plan}")
    for step_index, position in enumerate(plan, 1):
        data = click_data(position)
        result = env.step(game_action.ACTION6, data)
        trace.append(ClickStep(level=level, step=step_index, grid=position, data=data))
        final_level_count = int(getattr(result, "levels_completed", final_level_count))

        if not result.frame:
            return LevelRun(
                level=level,
                success=False,
                actions=step_index,
                plan=plan,
                trace=trace,
                final_level_count=final_level_count,
                reason=f"life lost after click {position}",
            )

        if final_level_count >= level:
            write(f"  completed L{level} at step {step_index}/{len(plan)}")
            return LevelRun(
                level=level,
                success=True,
                actions=step_index,
                plan=plan[:step_index],
                trace=trace,
                final_level_count=final_level_count,
            )

    write(f"  final snapshot: {json.dumps(snapshot(env._game), default=str)}")
    return LevelRun(
        level=level,
        success=False,
        actions=len(trace),
        plan=plan,
        trace=trace,
        final_level_count=final_level_count,
        reason="plan exhausted before level completion",
    )


def run(target_level: int = 4) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"target_L{target_level}"
    write, flush = log_sink(output_dir)
    runs: List[LevelRun] = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        max_level = len(env._game._levels)
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"SU15 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, PLANS[level], write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "target_level": effective_target,
            "success": success,
            "runs": [asdict(run) for run in runs],
            "total_actions": sum(run.actions for run in runs),
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve SU15 levels 1-4 by click merge plans.")
    parser.add_argument("--target-level", type=int, default=4)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
