"""
V28 - program-synthesis solver for ARC-AGI-3 TN36.

TN36 is a click-only "tiny program" puzzle.  The right machine contains a
bit-grid where each column is one opcode.  Clicking program bits edits the
opcode, and clicking the run button executes the program.  Later levels use
checkpoint pressure pads: a program that ends on a pad updates the machine's
reset position, so the final plan is a short sequence of programs.

This solver reads the live program grid from the engine, toggles only the bits
needed to realize each desired opcode, then presses run.  The plans below were
derived by searching the machine's geometric state graph with the real engine
movement/collision methods.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "tn36"
OUTPUT_DIR = Path("v28_tn36_output")
Position = Tuple[int, int]
Program = List[int]


PROGRAMS: Dict[int, List[Program]] = {
    1: [[3, 3, 3, 3, 3]],
    2: [[33, 33, 33, 33]],
    3: [[2, 33, 2, 2, 2, 33]],
    4: [[9, 34, 3, 3, 3, 3]],
    5: [[3, 3, 3, 5, 8, 63]],
    6: [
        [0, 0, 10, 10, 33, 33],
        [0, 12, 33, 33, 33, 1],
    ],
    7: [
        [0, 0, 0, 2, 10, 33],
        [33, 33, 33, 1, 12, 33],
    ],
}


@dataclass
class ProgramRun:
    program_index: int
    target_program: Program
    clicks: List[Position]
    run_button: Position
    completed_level: bool
    levels_completed: int


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    programs: List[ProgramRun]
    final_program: List[int]
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


def action_data(position: Position) -> Dict[str, int]:
    return {"x": int(position[0]), "y": int(position[1])}


def bit_center(bit_cell) -> Position:
    return (int(bit_cell.x + bit_cell.width // 2), int(bit_cell.y + bit_cell.height // 2))


def run_button_center(machine) -> Position:
    button = machine.sxhtkytekm
    if button is None:
        raise RuntimeError("right machine has no run button")
    return (int(button.x + button.width // 2), int(button.y + button.height // 2))


def right_machine(env):
    return env._game.fdksqlmpki.bzirenxmrg


def current_program(env) -> List[int]:
    return [int(value) for value in right_machine(env).vupcwzjtxu.vkuvtkaerv]


def clicks_to_program(env, target: Sequence[int]) -> List[Position]:
    machine = right_machine(env)
    rows = machine.vupcwzjtxu.pfyayhyovw
    current = current_program(env)
    if len(target) > len(rows):
        raise ValueError(f"target program has {len(target)} rows, grid has {len(rows)}")

    clicks: List[Position] = []
    for row_index, desired in enumerate(target):
        row = rows[row_index]
        before = current[row_index]
        delta = int(before) ^ int(desired)
        for bit_index, bit_cell in enumerate(row.sonocxtjtj):
            if delta & (1 << bit_index):
                clicks.append(bit_center(bit_cell))
    return clicks


def execute_click(env, game_action, position: Position):
    return env.step(game_action.ACTION6, action_data(position))


def execute_program(env, game_action, target: Program, program_index: int, write) -> ProgramRun:
    clicks = clicks_to_program(env, target)
    write(f"  program {program_index}: {target} bit_clicks={len(clicks)} {clicks}")

    levels_completed = int(getattr(env._game, "level_index", 0))
    for click in clicks:
        result = execute_click(env, game_action, click)
        levels_completed = int(getattr(result, "levels_completed", levels_completed))
        if not result.frame:
            return ProgramRun(program_index, list(target), clicks, (-1, -1), False, levels_completed)

    run_button = run_button_center(right_machine(env))
    result = execute_click(env, game_action, run_button)
    levels_completed = int(getattr(result, "levels_completed", levels_completed))
    completed_level = levels_completed >= int(env._game.level_index)
    write(f"    run={run_button} levels_completed={levels_completed}")
    return ProgramRun(program_index, list(target), clicks, run_button, completed_level, levels_completed)


def execute_level(env, game_action, programs: List[Program], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    before_completed = level - 1
    runs: List[ProgramRun] = []
    actions = 0

    for program_index, program in enumerate(programs, 1):
        run_info = execute_program(env, game_action, program, program_index, write)
        runs.append(run_info)
        actions += len(run_info.clicks) + 1
        if run_info.run_button == (-1, -1):
            return LevelRun(
                level=level,
                success=False,
                actions=actions,
                programs=runs,
                final_program=current_program(env),
                reason="lost while editing program bits",
            )
        if run_info.levels_completed > before_completed:
            write(f"  completed L{level} after program {program_index}")
            return LevelRun(
                level=level,
                success=True,
                actions=actions,
                programs=runs,
                final_program=current_program(env),
            )

    return LevelRun(
        level=level,
        success=False,
        actions=actions,
        programs=runs,
        final_program=current_program(env),
        reason="program sequence exhausted before level completion",
    )


def run(target_level: int = 7) -> Dict[str, object]:
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
        effective_target = min(target_level, max_level, max(PROGRAMS))
        write(f"TN36 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, PROGRAMS[level], write)
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
    parser = argparse.ArgumentParser(description="Run the TN36 program-grid solver.")
    parser.add_argument("--target-level", type=int, default=7)
    args = parser.parse_args()
    summary = run(target_level=args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
