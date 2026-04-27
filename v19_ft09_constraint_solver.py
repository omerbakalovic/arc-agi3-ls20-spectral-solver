"""
V19 - source-assisted constraint solver for ARC-AGI-3 FT09.

FT09 is a click/constraint puzzle.  Clickable cells cycle through a level
palette; clue tiles specify local same/different color constraints on adjacent
clickable cells.  The runner converts each click into a modulo-color operator
and solves the resulting constraint system before executing the clicks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "ft09"
OUTPUT_DIR = Path("v19_ft09_output")
CELL = 4
CLICK_TAGS = ("Hkx", "NTi")
CLUE_TAG = "bsT"

Pos = Tuple[int, int]


@dataclass(frozen=True)
class Cell:
    index: int
    name: str
    pos: Pos
    color_index: int
    tag: str


@dataclass
class Ft09Model:
    level: int
    palette: Tuple[int, ...]
    step_limit: int
    cells: List[Cell]
    effects: List[Set[int]]
    allowed: Dict[int, Set[int]]


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


def sprite_tags(sprite) -> Set[str]:
    return set(getattr(sprite, "tags", set()))


def sprite_pos(sprite) -> Pos:
    return int(sprite.x), int(sprite.y)


def center_color(sprite) -> int:
    return int(sprite.pixels[1][1])


def click_data(sprite) -> Dict[str, int]:
    # The FT09 camera maps 64 display pixels onto a 32x32 game grid.
    return {"x": 2 * (int(sprite.x) + int(sprite.width) // 2), "y": 2 * (int(sprite.y) + int(sprite.height) // 2)}


def click_sprites(game) -> List[object]:
    sprites = []
    seen = set()
    for tag in CLICK_TAGS:
        for sprite in game.current_level.get_sprites_by_tag(tag):
            if id(sprite) not in seen:
                sprites.append(sprite)
                seen.add(id(sprite))
    return sorted(sprites, key=lambda s: (int(s.y), int(s.x), s.name))


def click_kernel(sprite, default_kernel: Sequence[Sequence[int]]) -> List[List[int]]:
    if "NTi" in sprite_tags(sprite):
        kernel = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
        for row in range(3):
            for col in range(3):
                if int(sprite.pixels[row][col]) == 6:
                    kernel[row][col] = 1
        return kernel
    return [[int(v) for v in row] for row in default_kernel]


def extract_model(game) -> Ft09Model:
    palette = tuple(int(v) for v in game.gqb)
    default_kernel = game.irw
    sprites = click_sprites(game)
    by_pos = {sprite_pos(sprite): sprite for sprite in sprites}
    index_by_sprite = {id(sprite): i for i, sprite in enumerate(sprites)}

    cells = [
        Cell(
            index=i,
            name=sprite.name,
            pos=sprite_pos(sprite),
            color_index=palette.index(center_color(sprite)),
            tag="NTi" if "NTi" in sprite_tags(sprite) else "Hkx",
        )
        for i, sprite in enumerate(sprites)
    ]

    effects: List[Set[int]] = []
    for sprite in sprites:
        affected: Set[int] = set()
        kernel = click_kernel(sprite, default_kernel)
        for row in range(3):
            for col in range(3):
                if not kernel[row][col]:
                    continue
                target_pos = (int(sprite.x) + (col - 1) * CELL, int(sprite.y) + (row - 1) * CELL)
                target = by_pos.get(target_pos)
                if target is not None:
                    affected.add(index_by_sprite[id(target)])
        effects.append(affected)

    allowed: Dict[int, Set[int]] = {cell.index: set(range(len(palette))) for cell in cells}
    for clue in game.current_level.get_sprites_by_tag(CLUE_TAG):
        target_index = palette.index(center_color(clue))
        for row in range(3):
            for col in range(3):
                if row == 1 and col == 1:
                    continue
                pos = (int(clue.x) + (col - 1) * CELL, int(clue.y) + (row - 1) * CELL)
                sprite = by_pos.get(pos)
                if sprite is None:
                    continue
                cell_index = index_by_sprite[id(sprite)]
                same_required = int(clue.pixels[row][col]) == 0
                constraint = {target_index} if same_required else set(range(len(palette))) - {target_index}
                allowed[cell_index] &= constraint
                if not allowed[cell_index]:
                    raise ValueError(f"conflicting clue constraints at {pos}")

    return Ft09Model(
        level=int(game.level_index) + 1,
        palette=palette,
        step_limit=int(game.lpw.dzy),
        cells=cells,
        effects=effects,
        allowed=allowed,
    )


def solve_gf2(rows: List[int], rhs: List[int], width: int) -> Optional[List[int]]:
    matrix = [(row | (bit << width)) for row, bit in zip(rows, rhs)]
    rank = 0
    pivots: List[int] = []
    for col in range(width):
        pivot = next((r for r in range(rank, len(matrix)) if (matrix[r] >> col) & 1), None)
        if pivot is None:
            continue
        matrix[rank], matrix[pivot] = matrix[pivot], matrix[rank]
        for r in range(len(matrix)):
            if r != rank and ((matrix[r] >> col) & 1):
                matrix[r] ^= matrix[rank]
        pivots.append(col)
        rank += 1

    mask = (1 << width) - 1
    for row in matrix[rank:]:
        if (row & mask) == 0 and ((row >> width) & 1):
            return None

    solution = [0] * width
    for row_index, col in enumerate(pivots):
        solution[col] = (matrix[row_index] >> width) & 1
    return solution


def solve_binary_model(model: Ft09Model) -> Optional[List[int]]:
    rows: List[int] = []
    rhs: List[int] = []
    for cell in model.cells:
        allowed = model.allowed[cell.index]
        if len(allowed) != 1:
            continue
        desired = next(iter(allowed))
        row = 0
        for var, affected in enumerate(model.effects):
            if cell.index in affected:
                row |= 1 << var
        rows.append(row)
        rhs.append((desired - cell.color_index) % 2)
    return solve_gf2(rows, rhs, len(model.cells))


def solve_center_only_model(model: Ft09Model) -> Optional[List[int]]:
    plan = [0] * len(model.cells)
    for cell in model.cells:
        if model.effects[cell.index] != {cell.index}:
            return None
        allowed = model.allowed[cell.index]
        if cell.color_index in allowed:
            desired = cell.color_index
        else:
            desired = min(allowed, key=lambda idx: (idx - cell.color_index) % len(model.palette))
        plan[cell.index] = (desired - cell.color_index) % len(model.palette)
    return plan


def solve_model(model: Ft09Model) -> List[int]:
    if len(model.palette) == 2:
        solution = solve_binary_model(model)
    else:
        solution = solve_center_only_model(model)
    if solution is None:
        raise RuntimeError(f"no constraint solution for level {model.level}")
    return solution


def plan_clicks(model: Ft09Model, counts: Sequence[int]) -> List[int]:
    clicks: List[int] = []
    for index, count in enumerate(counts):
        clicks.extend([index] * int(count))
    return clicks


def execute_click_plan(env, game_action, model: Ft09Model, clicks: Sequence[int], write) -> Tuple[bool, int]:
    result = None
    sprites = click_sprites(env._game)
    for step_index, cell_index in enumerate(clicks, 1):
        sprite = sprites[cell_index]
        result = env.step(game_action.ACTION6, click_data(sprite))
        lvl = int(result.levels_completed)
        write(
            f"  [click {step_index:03d}] cell={cell_index:02d} "
            f"tag={model.cells[cell_index].tag} pos={model.cells[cell_index].pos} lvl={lvl}"
        )
        if lvl >= model.level:
            return True, lvl
        if not result.frame:
            return False, lvl
    final_level = int(result.levels_completed) if result is not None else model.level - 1
    return final_level >= model.level, final_level


def run(target_level: int = 6) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"target_L{target_level}"
    write, flush = log_sink(output_dir)
    runs: List[Dict[str, object]] = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        max_level = len(env._game._levels)
        effective_target = min(target_level, max_level)
        write(f"FT09 target={target_level} available={max_level} effective={effective_target}")

        for _ in range(1, effective_target + 1):
            model = extract_model(env._game)
            counts = solve_model(model)
            clicks = plan_clicks(model, counts)
            write(
                f"\n=== Level {model.level} ===\n"
                f"palette={list(model.palette)} cells={len(model.cells)} "
                f"constrained={sum(model.allowed[i] != set(range(len(model.palette))) for i in range(len(model.cells)))} "
                f"steps={model.step_limit} clicks={len(clicks)}"
            )
            write("click_counts=" + json.dumps({str(i): c for i, c in enumerate(counts) if c}))
            ok, final_level = execute_click_plan(env, GameAction, model, clicks, write)
            runs.append(
                {
                    "level": model.level,
                    "success": ok,
                    "actions": len(clicks),
                    "clicks": [model.cells[i].pos for i in clicks],
                    "final_level_count": final_level,
                }
            )
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{model.level}")
            if not ok:
                break

        success = bool(runs and runs[-1]["level"] == effective_target and runs[-1]["success"])
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(arc, write, "Final score", full=True)
        summary = {
            "requested_target_level": target_level,
            "target_level": effective_target,
            "success": success,
            "runs": runs,
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
