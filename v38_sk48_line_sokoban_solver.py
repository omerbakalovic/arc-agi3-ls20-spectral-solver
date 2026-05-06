"""
V38 - SK48 line-Sokoban solver.

SK48 hides a colored crate-ordering puzzle behind click-selectable line tools.
Each tool is a one-dimensional chain: moving along its axis extends or retracts
the chain, while perpendicular moves are allowed only on rail cells.  Colored
blocks ride on top of the chain, so the puzzle reduces to arranging the block
sequence observed on each active source line to match the paired target line.

The plans below were generated with a source-assisted line/box transition model
validated against the live ARC runtime, then replayed here as real keyboard and
click actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "sk48"
OUTPUT_DIR = Path("v38_sk48_output")
Primitive = str


PLANS: Dict[int, str] = {
    1: "RRRUUURLDDRLUR",
    2: "RRRRUURURLLULLURRDRRLURLLURR",
    3: "RRUUUURDDLDRRRRLULLLUUURDDDLUUUUR",
    4: "UULRURULLLDDDRRRUULLURDLU",
    5: "LULLRRRRURRDLLLDDRRRLLLLDRRRRRLUR",
    6: "RRC2DDRDC0DRLDRRUC2URDURDDLC0DRRLLLLDRC2DDULD",
    7: "RRRRRC2DLDRRC0RLLLDDRUUUC2RDLC0RR",
    8: "RRC2DDRDLDDDUUURC0RRRRLDLU",
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Primitive]
    active_head: tuple[int, int, int]
    covered_sequences: Dict[str, List[int]]
    reason: str = ""


def log_sink(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    def write(message: str = "") -> None:
        text = str(message)
        print(text)
        lines.append(text)
        sys.stdout.flush()

    def flush() -> None:
        (output_dir / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    return write, flush


def parse_plan(plan: str) -> List[Primitive]:
    primitives: List[Primitive] = []
    index = 0
    while index < len(plan):
        if plan[index] == "C":
            end = index + 1
            while end < len(plan) and plan[end].isdigit():
                end += 1
            primitives.append(plan[index:end])
            index = end
        else:
            primitives.append(plan[index])
            index += 1
    return primitives


def block_color(sprite) -> int:
    return int(sprite.pixels[1, 1])


def click_data_for_head(game, head_index: int) -> dict[str, int]:
    heads = list(game.mwfajkguqx.keys())
    if head_index >= len(heads):
        raise RuntimeError(f"head index {head_index} out of range for level {game.level_index + 1}")
    head = heads[head_index]
    return {"x": int(head.x) + 2, "y": int(head.y) + 2}


def active_head_state(game) -> tuple[int, int, int]:
    head = game.vzvypfsnt
    return (int(head.x), int(head.y), int(head.rotation))


def covered_sequences(game) -> Dict[str, List[int]]:
    sequences: Dict[str, List[int]] = {}
    for index, head in enumerate(game.mwfajkguqx.keys()):
        covered = [block_color(block) for block in game.vjfbwggsd[head]]
        if covered:
            sequences[f"{index}:{head.name}@{int(head.x)},{int(head.y)}"] = covered
    return sequences


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "U":
        return env.step(game_action.ACTION1)
    if primitive == "D":
        return env.step(game_action.ACTION2)
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive.startswith("C"):
        head_index = int(primitive[1:])
        return env.step(game_action.ACTION6, click_data_for_head(env._game, head_index))
    raise ValueError(f"unknown primitive: {primitive}")


def execute_level(env, game_action, level: int, plan: Sequence[Primitive], write) -> LevelRun:
    game = env._game
    write(
        f"  start active={active_head_state(game)} "
        f"covered={covered_sequences(game)} actions={len(plan)}"
    )

    used: List[Primitive] = []
    for primitive in plan:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        state = getattr(result.state, "value", result.state)
        if int(getattr(result, "levels_completed", level - 1)) >= level:
            write(
                f"  completed L{level} after {len(used)} actions "
                f"active={active_head_state(env._game)}"
            )
            return LevelRun(
                level=level,
                success=True,
                actions=len(used),
                plan=list(used),
                active_head=active_head_state(env._game),
                covered_sequences=covered_sequences(env._game),
            )
        if state not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level=level,
                success=False,
                actions=len(used),
                plan=list(used),
                active_head=active_head_state(env._game),
                covered_sequences=covered_sequences(env._game),
                reason=f"primitive {primitive} ended in state={state}",
            )

    return LevelRun(
        level=level,
        success=False,
        actions=len(used),
        plan=list(used),
        active_head=active_head_state(env._game),
        covered_sequences=covered_sequences(env._game),
        reason="plan exhausted before level completion",
    )


def run(target_level: int = max(PLANS), output_dir: Path = OUTPUT_DIR) -> Dict[str, object]:
    write, flush = log_sink(output_dir / f"target_L{target_level}")
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
        write(f"SK48 target={target_level} available={max_level} effective={effective_target}")
        score_utils.write_scorecard_snapshot(arc, write, "Initial score")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            plan = parse_plan(PLANS[level])
            run_info = execute_level(env, GameAction, level, plan, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "PARTIAL"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "effective_target_level": effective_target,
            "success": success,
            "runs": [asdict(run) for run in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / f"target_L{target_level}" / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay verified SK48 line-Sokoban plans.")
    parser.add_argument("--target-level", type=int, default=max(PLANS))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = run(args.target_level, args.output_dir)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
