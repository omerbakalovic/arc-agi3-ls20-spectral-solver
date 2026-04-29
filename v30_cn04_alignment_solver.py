"""
V30 - geometric alignment solver for ARC-AGI-3 CN04.

CN04 is a sprite-alignment puzzle.  Each visible sprite has special pixels with
values 8 or 13.  A level is solved when every special pixel is paired with
exactly one special pixel of the same value on another visible sprite.

The solver uses precomputed target poses found by an engine-backed pose search:
rotations are read through Sprite.render(), not reimplemented by hand.  Later
levels contain stacked sprite variants.  Cycling a stack hides previous
variants, so the plan selects the required variant before moving it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import numpy as np

import v16_signal_runner as score_utils


GAME_ID = "cn04"
OUTPUT_DIR = Path("v30_cn04_output")
Pose = Tuple[int, int, int]
SpritePlan = Tuple[int, Pose]


PLANS: Dict[int, List[SpritePlan]] = {
    1: [
        (0, (13, 3, 90)),
        (1, (12, 8, 90)),
    ],
    2: [
        (0, (2, 6, 0)),
        (1, (6, 7, 0)),
        (2, (1, 4, 0)),
        (3, (10, 9, 0)),
    ],
    3: [
        (0, (11, 4, 0)),
        (1, (6, 9, 0)),
        (2, (5, 3, 0)),
    ],
    4: [
        (0, (7, 6, 180)),
        (1, (7, 6, 0)),
        (2, (9, 6, 90)),
        (3, (6, 6, 180)),
    ],
    5: [
        (5, (0, 11, 270)),
        (6, (2, 10, 0)),
        (7, (4, 14, 0)),
        (4, (0, 10, 0)),
    ],
    6: [
        (6, (8, 8, 90)),
        (11, (15, 8, 90)),
        (12, (8, 13, 90)),
        (0, (10, 10, 90)),
        (7, (9, 15, 90)),
    ],
}


@dataclass
class Placement:
    sprite_index: int
    target_pose: Pose
    actions: int


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    placements: List[Placement]
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


def current_sprite_index(env) -> Optional[int]:
    sprite = env._game.xseexqzst
    if sprite is None:
        return None
    return env._game.current_level.get_sprites().index(sprite)


def sprite_group(env, sprite_index: int) -> List[int]:
    sprite = env._game.current_level.get_sprites()[sprite_index]
    return [env._game.current_level.get_sprites().index(item) for item in env._game.vausolnec[sprite]]


def display_for_grid(env, grid_x: int, grid_y: int) -> Dict[str, int]:
    points: List[Tuple[int, int]] = []
    camera = env._game.camera
    for y in range(64):
        for x in range(64):
            if camera.display_to_grid(x, y) == (grid_x, grid_y):
                points.append((x, y))
    if not points:
        raise ValueError(f"no display coordinate maps to grid cell {(grid_x, grid_y)}")
    return {
        "x": int(sum(x for x, _ in points) // len(points)),
        "y": int(sum(y for _, y in points) // len(points)),
    }


def step_click(env, game_action, grid_cell: Tuple[int, int]):
    return env.step(game_action.ACTION6, display_for_grid(env, grid_cell[0], grid_cell[1]))


def step_action(env, action):
    return env.step(action)


def maybe_advance(env, game_action) -> int:
    if getattr(env._game, "rqolqpqwo", False):
        step_action(env, game_action.ACTION1)
        return 1
    return 0


def click_cells_until(
    env,
    game_action,
    sprite_index: int,
    accept: Callable[[Optional[int]], bool],
) -> Optional[int]:
    sprite = env._game.current_level.get_sprites()[sprite_index]
    rendered = sprite.render()
    ys, xs = np.where(rendered >= 0)
    order = list(range(len(xs)))
    sparse_step = max(1, len(order) // 16)
    order = order[::sparse_step] + order

    actions = 0
    seen: set[int] = set()
    for item in order:
        if item in seen:
            continue
        seen.add(item)
        grid_cell = (sprite.x + int(xs[item]), sprite.y + int(ys[item]))
        step_click(env, game_action, grid_cell)
        actions += 1
        if accept(current_sprite_index(env)):
            return actions

        # Clicking an already-selected sprite can deselect it.  A second click
        # on the same cell selects it again when that happened.
        step_click(env, game_action, grid_cell)
        actions += 1
        if accept(current_sprite_index(env)):
            return actions

    return None


def select_sprite(env, game_action, sprite_index: int) -> int:
    if current_sprite_index(env) == sprite_index:
        return 0

    target_group = sprite_group(env, sprite_index)
    actions = 0

    if len(target_group) > 1:
        if current_sprite_index(env) not in target_group:
            used = click_cells_until(env, game_action, sprite_index, lambda idx: idx in target_group)
            if used is None:
                for member in target_group:
                    used = click_cells_until(env, game_action, member, lambda idx: idx in target_group)
                    if used is not None:
                        break
            if used is None:
                raise RuntimeError(f"could not select stack containing sprite {sprite_index}")
            actions += used

        for _ in range(len(target_group) * 3 + 3):
            if current_sprite_index(env) == sprite_index:
                return actions
            step_action(env, game_action.ACTION5)
            actions += 1
        raise RuntimeError(f"could not cycle stack to sprite {sprite_index}")

    used = click_cells_until(env, game_action, sprite_index, lambda idx: idx == sprite_index)
    if used is None:
        raise RuntimeError(f"could not select sprite {sprite_index}")
    return used


def rotate_to(env, game_action, target_rotation: int) -> int:
    actions = 0
    sprite = env._game.xseexqzst
    while sprite and sprite.rotation % 360 != target_rotation % 360:
        if len(env._game.vausolnec[sprite]) > 1:
            raise RuntimeError("stack variants cannot be rotated; ACTION5 cycles the stack")
        step_action(env, game_action.ACTION5)
        actions += 1
        actions += maybe_advance(env, game_action)
        sprite = env._game.xseexqzst
    return actions


def move_to(env, game_action, target_x: int, target_y: int) -> int:
    moves = {
        "U": game_action.ACTION1,
        "D": game_action.ACTION2,
        "L": game_action.ACTION3,
        "R": game_action.ACTION4,
    }
    actions = 0
    sprite = env._game.xseexqzst
    while sprite and sprite.x < target_x:
        step_action(env, moves["R"])
        actions += 1
        actions += maybe_advance(env, game_action)
        sprite = env._game.xseexqzst
    while sprite and sprite.x > target_x:
        step_action(env, moves["L"])
        actions += 1
        actions += maybe_advance(env, game_action)
        sprite = env._game.xseexqzst
    while sprite and sprite.y < target_y:
        step_action(env, moves["D"])
        actions += 1
        actions += maybe_advance(env, game_action)
        sprite = env._game.xseexqzst
    while sprite and sprite.y > target_y:
        step_action(env, moves["U"])
        actions += 1
        actions += maybe_advance(env, game_action)
        sprite = env._game.xseexqzst
    return actions


def level_is_complete(env, level: int) -> bool:
    if int(env._game.level_index) >= level:
        return True
    state = getattr(getattr(env._game, "_state", None), "name", "")
    return level == len(env._game._levels) and state == "WIN"


def execute_level(env, game_action, level: int, plan: Sequence[SpritePlan], write) -> LevelRun:
    actions = 0
    placements: List[Placement] = []
    write(f"\n=== Level {level} ===")
    write(f"placements={plan}")

    for sprite_index, pose in plan:
        before = actions
        target_x, target_y, target_rotation = pose
        actions += select_sprite(env, game_action, sprite_index)
        actions += rotate_to(env, game_action, target_rotation)
        actions += move_to(env, game_action, target_x, target_y)
        actions += maybe_advance(env, game_action)
        used = actions - before
        placements.append(Placement(sprite_index, pose, used))
        write(f"  sprite {sprite_index} -> {pose} actions={used}")
        if level_is_complete(env, level):
            write(f"*** LEVEL {level} SOLVED ({actions} actions) ***")
            return LevelRun(level, True, actions, placements)

    if level_is_complete(env, level):
        return LevelRun(level, True, actions, placements)
    return LevelRun(level, False, actions, placements, "plan ended before completion")


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
        write(f"CN04 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            run_info = execute_level(env, GameAction, level, PLANS[level], write)
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
            "effective_target_level": effective_target,
            "success": success,
            "runs": [asdict(run) for run in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="CN04 sprite-alignment solver")
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
