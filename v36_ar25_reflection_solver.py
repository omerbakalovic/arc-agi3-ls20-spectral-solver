"""
V36 - reflection-group solver for ARC-AGI-3 AR25.

AR25 is a geometric mirror puzzle.  Each movable shape induces an orbit under
the active mirror axes:

    vertical mirror:   (x, y) -> (2V - x, y)
    horizontal mirror: (x, y) -> (x, 2H - y)

The level is solved when the union of these direct/reflected shape cells covers
all target cells.  This runner enumerates integer mirror axes and piece
placements, chooses the lowest-move covering configuration, then replays it
against the live ARC runtime with real click/keyboard actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "ar25"
OUTPUT_DIR = Path("v36_ar25_output")
Primitive = str
Point = Tuple[int, int]
Axis = Tuple[str, int]


@dataclass
class Placement:
    x: int
    y: int
    target_mask: int
    move_cost: int


@dataclass
class ReflectionConfig:
    level: int
    total_move_cost: int
    horizontal_axis: Optional[int]
    vertical_axis: Optional[int]
    axis_move_cost: int
    placements: List[Placement]
    target_count: int


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    move_actions: int
    config: ReflectionConfig
    primitive_plan: List[Primitive]
    final_pieces: List[Tuple[str, int, int]]
    final_mirrors: List[Tuple[str, int, int]]
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


def action_name(action_id) -> str:
    return getattr(action_id, "name", str(action_id))


def occupied_offsets(sprite) -> List[Point]:
    offsets: List[Point] = []
    for dy, row in enumerate(sprite.pixels):
        for dx, value in enumerate(row):
            if int(value) != -1:
                offsets.append((dx, dy))
    return offsets


def occupied_cells(sprite, width: int, height: int) -> List[Point]:
    cells: List[Point] = []
    for dx, dy in occupied_offsets(sprite):
        x = int(sprite.x) + dx
        y = int(sprite.y) + dy
        if 0 <= x < width and 0 <= y < height:
            cells.append((x, y))
    return cells


def reflected_target_mask(
    shape_cells: Sequence[Point],
    x: int,
    y: int,
    axes: Sequence[Axis],
    target_index: Dict[Point, int],
) -> int:
    """Return a bit mask of target cells covered by one placed shape orbit."""
    mask = 0
    for dx, dy in shape_cells:
        start = (x + dx, y + dy)
        seen = {start}
        stack = [start]
        while stack:
            px, py = stack.pop()
            bit = target_index.get((px, py))
            if bit is not None:
                mask |= 1 << bit
            for axis_type, axis in axes:
                reflected = (2 * axis - px, py) if axis_type == "V" else (px, 2 * axis - py)
                if reflected not in seen:
                    seen.add(reflected)
                    stack.append(reflected)
    return mask


def keep_cheapest_by_mask(entries: Iterable[Placement]) -> List[Placement]:
    best: Dict[int, Placement] = {}
    for placement in entries:
        old = best.get(placement.target_mask)
        if old is None or placement.move_cost < old.move_cost:
            best[placement.target_mask] = placement
    result = list(best.values())
    result.sort(key=lambda p: (p.move_cost, -p.target_mask.bit_count(), p.x, p.y))
    return result


def find_reflection_config(game) -> ReflectionConfig:
    level = int(game.level_index) + 1
    width, height = game.current_level.grid_size
    pieces = list(game.ouurgkpbbjj)
    mirrors = list(game.jtkyjqznbnp)
    targets = sorted((int(sprite.x), int(sprite.y)) for sprite in game.fswikrcrdmx)
    target_index = {point: idx for idx, point in enumerate(targets)}
    full_mask = (1 << len(targets)) - 1

    horizontal_mirror = next((m for m in mirrors if "0002nuguepuujf" in m.tags), None)
    vertical_mirror = next((m for m in mirrors if "0054kgxrvfihgm" in m.tags), None)

    if horizontal_mirror is None:
        horizontal_values: Sequence[Optional[int]] = [None]
    elif "0056icpryeujyf" in horizontal_mirror.tags:
        horizontal_values = [int(horizontal_mirror.y)]
    else:
        horizontal_values = range(height)

    if vertical_mirror is None:
        vertical_values: Sequence[Optional[int]] = [None]
    elif "0056icpryeujyf" in vertical_mirror.tags:
        vertical_values = [int(vertical_mirror.x)]
    else:
        vertical_values = range(width)

    best: Optional[ReflectionConfig] = None

    for horizontal_axis in horizontal_values:
        for vertical_axis in vertical_values:
            axes: List[Axis] = []
            axis_cost = 0
            if horizontal_mirror is not None:
                assert horizontal_axis is not None
                axes.append(("H", horizontal_axis))
                if "0056icpryeujyf" not in horizontal_mirror.tags:
                    axis_cost += abs(horizontal_axis - int(horizontal_mirror.y))
            if vertical_mirror is not None:
                assert vertical_axis is not None
                axes.append(("V", vertical_axis))
                if "0056icpryeujyf" not in vertical_mirror.tags:
                    axis_cost += abs(vertical_axis - int(vertical_mirror.x))

            per_piece: List[List[Placement]] = []
            possible_union = 0
            for sprite in pieces:
                shape_cells = occupied_offsets(sprite)
                entries: List[Placement] = []
                for y in range(0, height - int(sprite.height) + 1):
                    for x in range(0, width - int(sprite.width) + 1):
                        mask = reflected_target_mask(shape_cells, x, y, axes, target_index)
                        if mask:
                            move_cost = abs(x - int(sprite.x)) + abs(y - int(sprite.y))
                            entries.append(Placement(x, y, mask, move_cost))
                            possible_union |= mask
                per_piece.append(keep_cheapest_by_mask(entries))

            if possible_union != full_mask:
                continue

            candidate = combine_piece_placements(
                level=level,
                full_mask=full_mask,
                horizontal_axis=horizontal_axis,
                vertical_axis=vertical_axis,
                axis_cost=axis_cost,
                per_piece=per_piece,
                target_count=len(targets),
            )
            if candidate is None:
                continue
            if best is None or candidate.total_move_cost < best.total_move_cost:
                best = candidate

    if best is None:
        raise RuntimeError(f"no reflection covering configuration found for level {level}")
    return best


def combine_piece_placements(
    level: int,
    full_mask: int,
    horizontal_axis: Optional[int],
    vertical_axis: Optional[int],
    axis_cost: int,
    per_piece: Sequence[Sequence[Placement]],
    target_count: int,
) -> Optional[ReflectionConfig]:
    if len(per_piece) == 1:
        best = min(
            (p for p in per_piece[0] if p.target_mask == full_mask),
            key=lambda p: p.move_cost,
            default=None,
        )
        if best is None:
            return None
        return ReflectionConfig(
            level=level,
            total_move_cost=axis_cost + best.move_cost,
            horizontal_axis=horizontal_axis,
            vertical_axis=vertical_axis,
            axis_move_cost=axis_cost,
            placements=[best],
            target_count=target_count,
        )

    if len(per_piece) != 2:
        raise NotImplementedError("AR25 solver currently supports one or two movable shapes")

    first, second = per_piece
    best_pair: Optional[Tuple[int, Placement, Placement]] = None
    # Keep the original piece order because execution uses game.ouurgkpbbjj order.
    for p0 in first:
        need = full_mask & ~p0.target_mask
        for p1 in second:
            if p1.target_mask & need == need:
                cost = axis_cost + p0.move_cost + p1.move_cost
                if best_pair is None or cost < best_pair[0]:
                    best_pair = (cost, p0, p1)
                break

    if best_pair is None:
        return None
    cost, p0, p1 = best_pair
    return ReflectionConfig(
        level=level,
        total_move_cost=cost,
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        axis_move_cost=axis_cost,
        placements=[p0, p1],
        target_count=target_count,
    )


def current_piece_state(game) -> List[Tuple[str, int, int]]:
    return [(sprite.name, int(sprite.x), int(sprite.y)) for sprite in game.ouurgkpbbjj]


def current_mirror_state(game) -> List[Tuple[str, int, int]]:
    return [(sprite.name, int(sprite.x), int(sprite.y)) for sprite in game.jtkyjqznbnp]


def click_data_for_grid(game, grid_x: int, grid_y: int) -> Dict[str, int]:
    matches: List[Point] = []
    for y in range(64):
        for x in range(64):
            if game.camera.display_to_grid(x, y) == (grid_x, grid_y):
                matches.append((x, y))
    if not matches:
        raise RuntimeError(f"no display coordinate maps to grid cell {(grid_x, grid_y)}")
    x, y = matches[len(matches) // 2]
    return {"x": int(x), "y": int(y)}


def sprite_contains_cell(sprite, cell: Point) -> bool:
    x, y = cell
    sx, sy = int(sprite.x), int(sprite.y)
    if not (sx <= x < sx + int(sprite.width) and sy <= y < sy + int(sprite.height)):
        return False
    return int(sprite.pixels[y - sy, x - sx]) != -1


def click_data_for_sprite(game, sprite) -> Dict[str, int]:
    width, height = game.current_level.grid_size
    candidates = occupied_cells(sprite, width, height)
    if not candidates:
        raise RuntimeError(f"sprite {sprite.name} has no visible clickable cell")

    def rank(cell: Point) -> Tuple[int, int, int, int]:
        other_piece = any(
            other is not sprite and sprite_contains_cell(other, cell)
            for other in game.ouurgkpbbjj
        )
        other_mirror = any(
            other is not sprite and sprite_contains_cell(other, cell)
            for other in game.jtkyjqznbnp
        )
        center_x = int(sprite.x) + int(sprite.width) // 2
        center_y = int(sprite.y) + int(sprite.height) // 2
        distance = abs(cell[0] - center_x) + abs(cell[1] - center_y)
        return (1 if other_piece else 0, 1 if other_mirror else 0, distance, cell[1] * width + cell[0])

    cell = min(candidates, key=rank)
    return click_data_for_grid(game, cell[0], cell[1])


def execute_input(env, game_action, primitive: Primitive, data: Optional[Dict[str, int]] = None):
    if primitive == "U":
        return env.step(game_action.ACTION1, data)
    if primitive == "D":
        return env.step(game_action.ACTION2, data)
    if primitive == "L":
        return env.step(game_action.ACTION3, data)
    if primitive == "R":
        return env.step(game_action.ACTION4, data)
    if primitive == "C":
        assert data is not None
        return env.step(game_action.ACTION6, data)
    if primitive == "ADV":
        return env.step(game_action.ACTION5, data)
    raise ValueError(f"unknown primitive: {primitive}")


def select_sprite(env, game_action, sprite, primitives: List[Primitive]) -> Optional[str]:
    game = env._game
    if game.yvifanjrcyu is sprite:
        return None
    data = click_data_for_sprite(game, sprite)
    result = execute_input(env, game_action, "C", data)
    primitives.append(f"C@{data['x']},{data['y']}")
    state = getattr(result.state, "value", result.state)
    if state not in {"NOT_FINISHED", "WIN"}:
        return f"game state became {state} after selecting {sprite.name}"
    if game.yvifanjrcyu is sprite:
        return None

    # Fallback for rare ambiguous mirror intersections.
    for _ in range(len(game.ayyvxqrhnzw)):
        result = execute_input(env, game_action, "ADV")
        primitives.append("SEL")
        state = getattr(result.state, "value", result.state)
        if state not in {"NOT_FINISHED", "WIN"}:
            return f"game state became {state} while cycling selection"
        if game.yvifanjrcyu is sprite:
            return None
    return f"could not select {sprite.name}; selected={getattr(game.yvifanjrcyu, 'name', None)}"


def move_selected_to(
    env,
    game_action,
    sprite,
    target_x: int,
    target_y: int,
    primitives: List[Primitive],
    target_completed: int,
) -> Tuple[bool, Optional[str]]:
    err = select_sprite(env, game_action, sprite, primitives)
    if err:
        return False, err

    moves: List[Primitive] = []
    dx = target_x - int(sprite.x)
    dy = target_y - int(sprite.y)
    moves.extend(["R"] * max(0, dx))
    moves.extend(["L"] * max(0, -dx))
    moves.extend(["D"] * max(0, dy))
    moves.extend(["U"] * max(0, -dy))

    for primitive in moves:
        before = (int(sprite.x), int(sprite.y))
        result = execute_input(env, game_action, primitive)
        primitives.append(primitive)
        state = getattr(result.state, "value", result.state)
        if int(getattr(result, "levels_completed", target_completed - 1)) >= target_completed:
            return True, None
        if state not in {"NOT_FINISHED", "WIN"}:
            return False, f"game state became {state} after {primitive}"
        after = (int(sprite.x), int(sprite.y))
        if before == after:
            return False, f"{sprite.name} did not move on {primitive}"
    return False, None


def execute_level(env, game_action, config: ReflectionConfig, write) -> LevelRun:
    game = env._game
    level = int(game.level_index) + 1
    target_completed = level
    primitives: List[Primitive] = []
    write(
        f"  config cost={config.total_move_cost} H={config.horizontal_axis} V={config.vertical_axis} "
        f"placements={[(p.x, p.y, p.move_cost, p.target_mask.bit_count()) for p in config.placements]}"
    )
    write(
        f"  start pieces={current_piece_state(game)} mirrors={current_mirror_state(game)} "
        f"steps={getattr(game.lelsvjlwneo, 'current_steps', None)}"
    )

    horizontal_mirror = next((m for m in game.jtkyjqznbnp if "0002nuguepuujf" in m.tags), None)
    vertical_mirror = next((m for m in game.jtkyjqznbnp if "0054kgxrvfihgm" in m.tags and "0056icpryeujyf" not in m.tags), None)

    move_count = 0
    for sprite, target_x, target_y in [
        (horizontal_mirror, None, config.horizontal_axis),
        (vertical_mirror, config.vertical_axis, None),
    ]:
        if sprite is None:
            continue
        solved, reason = move_selected_to(
            env,
            game_action,
            sprite,
            int(sprite.x) if target_x is None else int(target_x),
            int(sprite.y) if target_y is None else int(target_y),
            primitives,
            target_completed,
        )
        move_count = sum(1 for p in primitives if p in {"U", "D", "L", "R"})
        if solved:
            return LevelRun(level, True, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game))
        if reason:
            return LevelRun(level, False, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game), reason)

    for sprite, placement in zip(game.ouurgkpbbjj, config.placements):
        solved, reason = move_selected_to(
            env,
            game_action,
            sprite,
            placement.x,
            placement.y,
            primitives,
            target_completed,
        )
        move_count = sum(1 for p in primitives if p in {"U", "D", "L", "R"})
        if solved:
            return LevelRun(level, True, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game))
        if reason:
            return LevelRun(level, False, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game), reason)

    if int(getattr(env, "levels_completed", level - 1)) >= target_completed:
        return LevelRun(level, True, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game))

    if getattr(game, "hujpxmlafgh", False):
        result = execute_input(env, game_action, "ADV")
        primitives.append("ADV")
        if int(getattr(result, "levels_completed", level - 1)) >= target_completed:
            return LevelRun(level, True, len(primitives), move_count, config, primitives, current_piece_state(game), current_mirror_state(game))

    return LevelRun(
        level=level,
        success=False,
        actions=len(primitives),
        move_actions=move_count,
        config=config,
        primitive_plan=primitives,
        final_pieces=current_piece_state(game),
        final_mirrors=current_mirror_state(game),
        reason="configuration replay ended before level completion",
    )


def config_to_dict(config: ReflectionConfig) -> Dict[str, object]:
    data = asdict(config)
    data["placements"] = [asdict(p) for p in config.placements]
    return data


def run(target_level: int = 8) -> Dict[str, object]:
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
        write(f"AR25 target={target_level} available={max_level} effective={effective_target}")

        for _ in range(effective_target):
            level = int(env._game.level_index) + 1
            write(f"\n=== Level {level} ===")
            config = find_reflection_config(env._game)
            run_info = execute_level(env, GameAction, config, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break
            write(
                f"  completed L{level}: actions={run_info.actions} moves={run_info.move_actions} "
                f"pieces={run_info.final_pieces} mirrors={run_info.final_mirrors}"
            )

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "PARTIAL"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "effective_target_level": effective_target,
            "success": success,
            "runs": [
                {
                    **asdict(run),
                    "config": config_to_dict(run.config),
                }
                for run in runs
            ],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=8)
    args = parser.parse_args()
    summary = run(args.target_level)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
