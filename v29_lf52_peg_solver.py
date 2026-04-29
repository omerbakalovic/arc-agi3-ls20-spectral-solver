"""
V29 - partial peg/conveyor solver for ARC-AGI-3 LF52.

LF52 behaves like peg solitaire with movable landing cells.  A click on a
piece exposes legal two-cell jumps; arrow actions move every active
``hupkpseyuim2`` cell along rail cells and carry any piece or bridge marker
that sits on that active cell.

The plans below were generated with a multiset cell model: unlike the first
prototype, it allows pieces, bridge markers, and active cells to stack on the
same coordinate, which is required by the live engine.  The solver is verified
end-to-end for levels 1-6.  Level 7 is intentionally left open; it needs a
longer sequence-planning layer rather than another local reactive jump.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple, Union
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "lf52"
OUTPUT_DIR = Path("v29_lf52_output")
Cell = Tuple[int, int]
Move = Tuple[str, str]
Jump = Tuple[str, Cell, Cell]
MacroAction = Union[Move, Jump]


PLANS: Dict[int, List[MacroAction]] = {
    1: [
        ("J", (1, 2), (3, 2)),
        ("J", (3, 2), (5, 2)),
        ("J", (5, 2), (5, 4)),
        ("J", (5, 4), (5, 6)),
    ],
    2: [
        ("J", (1, 1), (3, 1)),
        ("J", (3, 1), (5, 1)),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "U"),
        ("M", "U"),
        ("M", "U"),
        ("M", "L"),
        ("J", (5, 1), (7, 1)),
        ("M", "R"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("J", (5, 7), (7, 7)),
    ],
    3: [
        ("J", (1, 1), (1, 3)),
        ("J", (1, 3), (3, 3)),
        ("J", (3, 3), (3, 1)),
        ("J", (12, 2), (10, 2)),
        ("J", (12, 4), (10, 4)),
        ("M", "L"),
        ("J", (3, 1), (5, 1)),
        ("M", "R"),
        ("M", "R"),
        ("M", "U"),
        ("M", "U"),
        ("M", "R"),
        ("J", (8, 1), (10, 1)),
        ("J", (10, 1), (10, 3)),
        ("J", (10, 3), (10, 5)),
        ("J", (10, 5), (10, 7)),
        ("M", "R"),
        ("M", "D"),
        ("M", "D"),
        ("M", "R"),
        ("J", (11, 7), (9, 7)),
        ("M", "L"),
        ("M", "U"),
        ("M", "U"),
        ("M", "L"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "L"),
        ("M", "L"),
        ("J", (4, 7), (2, 7)),
        ("J", (1, 7), (3, 7)),
    ],
    4: [
        ("M", "L"),
        ("J", (1, 3), (3, 3)),
        ("J", (3, 3), (5, 3)),
        ("J", (5, 3), (7, 3)),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("J", (11, 3), (13, 3)),
        ("J", (13, 3), (13, 5)),
        ("J", (13, 5), (13, 7)),
        ("J", (16, 3), (16, 5)),
        ("J", (16, 5), (16, 7)),
        ("J", (16, 7), (14, 7)),
        ("J", (14, 7), (12, 7)),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("J", (8, 9), (8, 11)),
        ("M", "L"),
        ("M", "L"),
        ("J", (6, 11), (6, 13)),
        ("J", (6, 13), (4, 13)),
        ("M", "L"),
        ("M", "L"),
        ("J", (4, 13), (4, 11)),
        ("J", (4, 11), (4, 9)),
        ("J", (4, 9), (6, 9)),
    ],
    5: [
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "L"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "R"),
        ("M", "R"),
        ("M", "D"),
        ("M", "R"),
        ("M", "U"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("J", (1, 3), (3, 3)),
        ("J", (3, 3), (5, 3)),
        ("M", "U"),
        ("M", "U"),
        ("J", (5, 3), (7, 3)),
        ("M", "U"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "D"),
        ("J", (10, 3), (12, 3)),
        ("J", (12, 3), (14, 3)),
        ("M", "U"),
        ("M", "U"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "D"),
        ("M", "D"),
        ("J", (14, 3), (16, 3)),
        ("J", (16, 3), (18, 3)),
        ("J", (18, 4), (18, 2)),
        ("M", "U"),
        ("M", "U"),
        ("M", "R"),
        ("J", (18, 2), (18, 0)),
        ("J", (19, 0), (17, 0)),
        ("M", "L"),
        ("M", "L"),
        ("M", "L"),
        ("J", (17, 0), (15, 0)),
        ("J", (15, 0), (15, 2)),
        ("M", "L"),
        ("M", "L"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "D"),
        ("M", "R"),
        ("M", "R"),
        ("J", (15, 2), (15, 4)),
        ("J", (15, 4), (15, 6)),
        ("J", (15, 6), (15, 8)),
        ("J", (16, 8), (14, 8)),
    ],
    6: [
        ("J", (2, 2), (2, 4)),
        ("J", (2, 3), (2, 5)),
        ("J", (2, 4), (2, 6)),
        ("J", (2, 5), (2, 7)),
        ("J", (1, 7), (3, 7)),
        ("J", (3, 8), (3, 6)),
        ("M", "D"),
        ("M", "D"),
        ("J", (2, 6), (4, 6)),
        ("J", (3, 6), (5, 6)),
        ("J", (4, 6), (6, 6)),
        ("J", (5, 6), (7, 6)),
        ("J", (6, 6), (8, 6)),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "R"),
        ("M", "U"),
        ("M", "U"),
        ("J", (14, 4), (14, 2)),
        ("J", (14, 2), (16, 2)),
        ("M", "R"),
        ("M", "R"),
        ("M", "U"),
        ("M", "U"),
        ("J", (17, 4), (17, 2)),
        ("J", (16, 2), (18, 2)),
        ("J", (17, 2), (19, 2)),
        ("J", (18, 2), (20, 2)),
        ("J", (19, 2), (21, 2)),
        ("J", (20, 2), (22, 2)),
        ("J", (21, 2), (23, 2)),
        ("J", (22, 2), (24, 2)),
        ("J", (23, 2), (25, 2)),
        ("J", (24, 2), (26, 2)),
        ("J", (26, 2), (26, 4)),
        ("M", "D"),
        ("M", "D"),
        ("J", (26, 4), (24, 4)),
        ("M", "D"),
        ("M", "D"),
        ("M", "L"),
        ("M", "L"),
        ("M", "U"),
        ("M", "U"),
        ("J", (24, 4), (22, 4)),
        ("J", (22, 4), (22, 6)),
        ("M", "D"),
        ("M", "D"),
        ("J", (23, 6), (21, 6)),
        ("J", (22, 6), (20, 6)),
        ("J", (20, 6), (20, 8)),
    ],
}


@dataclass
class LevelRun:
    level: int
    success: bool
    macro_steps: int
    actions: int
    completed_at_macro: int | None
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


def cell_center(env, cell: Cell) -> Dict[str, int]:
    grid = env._game.ikhhdzfmarl.hncnfaqaddg
    offset_x, offset_y = grid.cdpcbbnfdp
    return {"x": int(offset_x + cell[0] * 6 + 3), "y": int(offset_y + cell[1] * 6 + 3)}


def move_actions(game_action) -> Dict[str, object]:
    return {
        "U": game_action.ACTION1,
        "D": game_action.ACTION2,
        "L": game_action.ACTION3,
        "R": game_action.ACTION4,
    }


def execute_jump(env, game_action, source: Cell, target: Cell):
    result = env.step(game_action.ACTION6, cell_center(env, source))
    if not result.frame:
        return result, 1
    result = env.step(game_action.ACTION6, cell_center(env, target))
    return result, 2


def execute_level(env, game_action, level: int, plan: Sequence[MacroAction], write) -> LevelRun:
    before_index = int(env._game.level_index)
    actions = 0
    moves = move_actions(game_action)
    write(f"\n=== Level {level} ===")
    write(f"macro_steps={len(plan)}")

    for step_index, action in enumerate(plan, 1):
        if action[0] == "M":
            direction = action[1]
            result = env.step(moves[direction])
            actions += 1
            write(f"  [{step_index:02d}] move {direction}")
        else:
            source, target = action[1], action[2]
            result, used = execute_jump(env, game_action, source, target)
            actions += used
            write(f"  [{step_index:02d}] jump {source}->{target}")

        if not result.frame:
            return LevelRun(level, False, len(plan), actions, None, "life lost")

        if int(env._game.level_index) > before_index:
            write(f"*** LEVEL {level} SOLVED at macro {step_index} ({actions} actions) ***")
            return LevelRun(level, True, len(plan), actions, step_index)

    return LevelRun(level, False, len(plan), actions, None, "plan ended before completion")


def run(target_level: int = 6) -> Dict[str, object]:
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
        effective_target = min(target_level, max_level)
        write(f"LF52 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            plan = PLANS.get(level)
            if plan is None:
                write(f"\n=== Level {level} ===")
                write("No verified plan yet; stopping honestly.")
                break
            run_info = execute_level(env, GameAction, level, plan, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break

        levels_solved = sum(1 for run in runs if run.success)
        success = levels_solved >= effective_target
        write("\nFINAL: " + ("SUCCESS" if success else "PARTIAL"))
        if target_level > max(PLANS):
            write("Open problem: Level 7 needs long-horizon sequence planning.")
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "effective_target_level": effective_target,
            "success": success,
            "levels_solved": levels_solved,
            "runs": [asdict(run) for run in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="LF52 partial peg/conveyor solver")
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
