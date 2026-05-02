"""
V34 - spectral/flow-routing solver for ARC-AGI-3 SP80.

SP80 is a click-and-keyboard fluid puzzle.  The player does not move; instead
the solver selects movable barriers, translates them on the board, and then
starts the spill simulation.  Each level is solved by placing reflectors so the
Laplace-like flow front fills every cup while avoiding fail boundaries.

The target barrier configurations were found with a lightweight symbolic flow
simulator, then verified against the live ARC engine.  The executor below uses
real clicks and direction actions, including the game's 180-degree input
rotation on levels 2, 3, and 5.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "sp80"
OUTPUT_DIR = Path("v34_sp80_output")

MovePlan = Tuple[int, str]
Primitive = str


PLANS: Dict[int, List[MovePlan]] = {
    1: [(0, "RRR")],
    2: [(2, "LL"), (1, "LLL")],
    3: [(3, "L"), (1, "RR"), (2, "RR"), (0, "L")],
    4: [
        (3, "LDDD"),
        (2, "D"),
        (1, "LL"),
        (4, "DDDDDDRRRRRRRR"),
        (0, "LLLLLUUUU"),
    ],
    5: [
        (2, "RRRUU"),
        (3, "RRDD"),
        (1, "RR"),
        (0, "LLLLLLLDD"),
    ],
    6: [
        (1, "DDD"),
        (3, "DDDDD"),
        (2, "LUUUUUU"),
        (0, "LLLLLLLLDDDD"),
    ],
}


TARGET_CONFIGS: Dict[int, List[Tuple[int, int]]] = {
    1: [(6, 4)],
    2: [(6, 9), (8, 11), (4, 6)],
    3: [(9, 10), (3, 8), (10, 7), (0, 5)],
    4: [(7, 9), (12, 10), (12, 6), (4, 8), (10, 15)],
    5: [(4, 11), (9, 13), (5, 7), (10, 7)],
    6: [(6, 8), (7, 13), (8, 8), (9, 10)],
}


INTERNAL_TO_INPUT = {
    0: {"U": "U", "D": "D", "L": "L", "R": "R"},
    1: {"U": "L", "D": "R", "L": "D", "R": "U"},
    2: {"U": "D", "D": "U", "L": "R", "R": "L"},
    3: {"U": "R", "D": "L", "L": "U", "R": "D"},
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    primitive_plan: List[Primitive]
    config: List[Tuple[int, int]]
    target_config: List[Tuple[int, int]]
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


def current_config(env) -> List[Tuple[int, int]]:
    return [
        (int(sprite.x), int(sprite.y))
        for sprite in env._game.fbrwmvzsym()
    ]


def selected_index(env) -> int:
    selected = env._game.vsoxmtrhqt
    for index, sprite in enumerate(env._game.fbrwmvzsym()):
        if sprite is selected:
            return index
    return -1


def click_data_for_sprite(env, sprite) -> Dict[str, int]:
    game = env._game
    grid_w, grid_h = game.current_level.grid_size
    cx = int((int(sprite.x) + int(sprite.width) / 2) * 64 / grid_w)
    cy = int((int(sprite.y) + int(sprite.height) / 2) * 64 / grid_h)
    k = int(game.fahhoimkk)
    if k == 0:
        x, y = cx, cy
    elif k == 1:
        x, y = cy, 63 - cx
    elif k == 2:
        x, y = 63 - cx, 63 - cy
    else:
        x, y = 63 - cy, cx
    return {"x": int(x), "y": int(y)}


def execute_input(env, game_action, action: str, data: Dict[str, int] | None = None):
    if action == "U":
        return env.step(game_action.ACTION1, data)
    if action == "D":
        return env.step(game_action.ACTION2, data)
    if action == "L":
        return env.step(game_action.ACTION3, data)
    if action == "R":
        return env.step(game_action.ACTION4, data)
    if action == "C":
        assert data is not None
        return env.step(game_action.ACTION6, data)
    if action == "S":
        return env.step(game_action.ACTION5)
    raise ValueError(f"unknown primitive action: {action}")


def execute_internal_move(env, game_action, direction: str):
    input_direction = INTERNAL_TO_INPUT[int(env._game.fahhoimkk)][direction]
    return execute_input(env, game_action, input_direction)


def execute_level(env, game_action, plan: Sequence[MovePlan], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    before_completed = level - 1
    primitives: List[Primitive] = []
    write(
        f"  start config={current_config(env)} selected={selected_index(env)} "
        f"rotation={env._game.fahhoimkk} steps={env._game.zlhbnhpcq}"
    )

    for piece_index, moves in plan:
        pieces = env._game.fbrwmvzsym()
        piece = pieces[piece_index]
        if env._game.vsoxmtrhqt is not piece:
            data = click_data_for_sprite(env, piece)
            primitives.append(f"C{piece_index}@{data['x']},{data['y']}")
            result = execute_input(env, game_action, "C", data)
            if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
                return LevelRun(
                    level=level,
                    success=False,
                    actions=len(primitives),
                    primitive_plan=primitives,
                    config=current_config(env),
                    target_config=TARGET_CONFIGS[level],
                    reason=f"game state became {getattr(result.state, 'value', result.state)} after click",
                )

        for direction in moves:
            before = current_config(env)[piece_index]
            primitives.append(direction)
            result = execute_internal_move(env, game_action, direction)
            after = current_config(env)[piece_index]
            if before == after:
                return LevelRun(
                    level=level,
                    success=False,
                    actions=len(primitives),
                    primitive_plan=primitives,
                    config=current_config(env),
                    target_config=TARGET_CONFIGS[level],
                    reason=f"piece {piece_index} did not move on {direction}",
                )
            if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
                return LevelRun(
                    level=level,
                    success=False,
                    actions=len(primitives),
                    primitive_plan=primitives,
                    config=current_config(env),
                    target_config=TARGET_CONFIGS[level],
                    reason=f"game state became {getattr(result.state, 'value', result.state)}",
                )

    config = current_config(env)
    write(f"  routed config={config}")
    if config != TARGET_CONFIGS[level]:
        return LevelRun(
            level=level,
            success=False,
            actions=len(primitives),
            primitive_plan=primitives,
            config=config,
            target_config=TARGET_CONFIGS[level],
            reason="configured barriers do not match verified target",
        )

    primitives.append("S")
    result = execute_input(env, game_action, "S")
    if int(getattr(result, "levels_completed", before_completed)) >= level:
        write(
            f"  completed L{level} after {len(primitives)} actions "
            f"state={getattr(result.state, 'value', result.state)}"
        )
        return LevelRun(
            level=level,
            success=True,
            actions=len(primitives),
            primitive_plan=primitives,
            config=config,
            target_config=TARGET_CONFIGS[level],
        )

    return LevelRun(
        level=level,
        success=False,
        actions=len(primitives),
        primitive_plan=primitives,
        config=current_config(env),
        target_config=TARGET_CONFIGS[level],
        reason=(
            f"spill ended without completing level; "
            f"state={getattr(result.state, 'value', result.state)} spills={env._game.lyremoheq}"
        ),
    )


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
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"SP80 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, PLANS[level], write)
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
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    summary = run(args.target_level)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
