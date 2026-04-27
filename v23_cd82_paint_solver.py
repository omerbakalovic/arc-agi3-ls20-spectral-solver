"""
V23 - symbolic paint-primitive solver for ARC-AGI-3 CD82.

CD82 is a compact drawing puzzle.  The live canvas is a 10x10 pixel signal and
the available actions select a color, move an eight-position brush, and paint
one of a small set of half-plane or strip primitives.

The solver reads the target pixels from the local public environment source,
decomposes the target by reverse-peeling paint primitives, then compiles those
strokes into real ARC keyboard/click actions and replays them against the live
runtime.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import numpy as np

import v16_signal_runner as score_utils


GAME_ID = "cd82"
OUTPUT_DIR = Path("v23_cd82_output")


@dataclass(frozen=True)
class Region:
    name: str
    kind: str
    position: int
    bits: int
    area: int


@dataclass(frozen=True)
class Stroke:
    kind: str
    position: int
    color: int


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


def mask_without_diagonals() -> np.ndarray:
    mask = np.ones((10, 10), dtype=bool)
    for i in range(10):
        mask[i, i] = False
        mask[i, 9 - i] = False
    return mask


MASK = mask_without_diagonals()
CELLS = [(r, c) for r in range(10) for c in range(10) if MASK[r, c]]
CELL_INDEX = {cell: i for i, cell in enumerate(CELLS)}


def bit_count(bits: int) -> int:
    return int(bits.bit_count())


def region_array(game, kind: str, position: int) -> np.ndarray:
    region = np.zeros((10, 10), dtype=bool)
    if kind == "basket":
        brush_kind, _, _, rotation, _, _ = game.nicoqsvlg[position]
        if brush_kind == "horizontal":
            if rotation == 180:
                region[0:5, :] = True
            elif rotation == 0:
                region[5:10, :] = True
            elif rotation == 90:
                region[:, 0:5] = True
            elif rotation == 270:
                region[:, 5:10] = True
        elif rotation == 180:
            for i in range(10):
                region[i, 0 : i + 1] = True
        elif rotation == 90:
            for i in range(10):
                region[i, 9 - i : 10] = True
        elif rotation == 0:
            for i in range(10):
                region[i, i:10] = True
        elif rotation == 270:
            for i in range(10):
                region[i, 0 : 10 - i] = True
    elif position == 0:
        region[0:3, 3:7] = True
    elif position == 4:
        region[7:10, 3:7] = True
    elif position == 6:
        region[3:7, 0:3] = True
    elif position == 2:
        region[3:7, 7:10] = True
    return region & MASK


def region_bits(mask: np.ndarray) -> int:
    bits = 0
    for (r, c), idx in CELL_INDEX.items():
        if bool(mask[r, c]):
            bits |= 1 << idx
    return bits


def build_regions(game) -> List[Region]:
    regions: List[Region] = []
    for position in range(8):
        mask = region_array(game, "basket", position)
        regions.append(
            Region(
                name=f"B{position}",
                kind="basket",
                position=position,
                bits=region_bits(mask),
                area=int(mask.sum()),
            )
        )
    if game.yxjfgsdkm:
        for position in [0, 2, 4, 6]:
            mask = region_array(game, "arrow", position)
            regions.append(
                Region(
                    name=f"A{position}",
                    kind="arrow",
                    position=position,
                    bits=region_bits(mask),
                    area=int(mask.sum()),
                )
            )
    return regions


def target_pixels(game) -> np.ndarray:
    targets = [
        sprite
        for sprite in game.current_level.get_sprites()
        if sprite.name.startswith("eoqnvkspoa-")
    ]
    if not targets:
        raise RuntimeError("CD82 target sprite not found")
    return np.array(targets[0].pixels, dtype=int)


def available_colors(game) -> List[int]:
    colors: List[int] = []
    for sprite in game.current_level.get_sprites():
        if sprite.name.startswith("pqkenviek"):
            colors.append(int(sprite.pixels[2, 2]))
    return colors


def solve_strokes(game, max_depth: int = 12) -> List[Stroke]:
    """Solve by peeling final paint layers backward from the target image."""
    target = target_pixels(game)
    colors = set(available_colors(game))
    regions = build_regions(game)
    target_values = [int(target[r, c]) for r, c in CELLS]
    all_bits = (1 << len(CELLS)) - 1

    def nonzero_remaining(bits: int) -> int:
        return sum(
            1
            for idx, value in enumerate(target_values)
            if ((bits >> idx) & 1) and value != 0
        )

    def uniform_value(bits: int) -> Optional[int]:
        values = {
            target_values[idx]
            for idx in range(len(target_values))
            if (bits >> idx) & 1
        }
        if len(values) != 1:
            return None
        return values.pop()

    def search(bits: int, depth: int, seen: set[Tuple[int, int]]) -> Optional[List[Stroke]]:
        if nonzero_remaining(bits) == 0:
            return []
        if depth == 0 or (bits, depth) in seen:
            return None

        candidates: List[Tuple[int, int, Region, int, int]] = []
        current_nonzero = nonzero_remaining(bits)
        for region in regions:
            intersection = bits & region.bits
            if not intersection:
                continue
            color = uniform_value(intersection)
            if color is None or color not in colors:
                continue
            new_bits = bits & ~intersection
            removed_nonzero = current_nonzero - nonzero_remaining(new_bits)
            candidates.append(
                (removed_nonzero, bit_count(intersection), region, color, new_bits)
            )

        candidates.sort(key=lambda item: (item[0] > 0, item[0], item[1]), reverse=True)
        for _, _, region, color, new_bits in candidates:
            tail = search(new_bits, depth - 1, seen)
            if tail is not None:
                return [Stroke(region.kind, region.position, color), *tail]

        seen.add((bits, depth))
        return None

    for depth in range(1, max_depth + 1):
        result = search(all_bits, depth, set())
        if result is not None:
            return list(reversed(result))
    raise RuntimeError("No CD82 paint decomposition found")


MOVE_CHARS = {1: "L", 2: "R", 3: "U", 4: "D"}
ACTION_BY_CHAR = {"L": 1, "R": 2, "U": 3, "D": 4}


def neighbor_positions(game, position: int) -> List[Tuple[int, str]]:
    x, y = game.nfhykrqjp[position]
    candidates = [
        (1, (max(0, x - 1), y)),
        (2, (min(2, x + 1), y)),
        (3, (x, max(0, y - 1))),
        (4, (x, min(2, y + 1))),
    ]
    neighbors: List[Tuple[int, str]] = []
    for action, xy in candidates:
        if xy == (1, 1):
            continue
        next_position = game.fbnqejrbl.get(xy)
        if next_position is not None and next_position != position:
            neighbors.append((next_position, MOVE_CHARS[action]))
    return neighbors


def shortest_position_path(game, start: int, goal: int) -> str:
    queue = deque([(start, "")])
    seen = {start}
    while queue:
        position, path = queue.popleft()
        if position == goal:
            return path
        for next_position, action in neighbor_positions(game, position):
            if next_position not in seen:
                seen.add(next_position)
                queue.append((next_position, path + action))
    raise RuntimeError(f"No brush path from {start} to {goal}")


def scalar(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def click_data_for_swatch(game, color: int) -> Dict[str, int | float]:
    scale, offset_x, offset_y = game.camera._calculate_scale_and_offset()
    for sprite in game.current_level.get_sprites():
        if sprite.name.startswith("pqkenviek") and int(sprite.pixels[2, 2]) == color:
            return {
                "x": scalar((sprite.x + 2) * scale + offset_x),
                "y": scalar((sprite.y + 2) * scale + offset_y),
            }
    raise RuntimeError(f"No swatch for color {color}")


def click_data_for_arrow(game) -> Dict[str, int | float]:
    action_inputs = game.bmwcxxvjum()
    if not action_inputs:
        raise RuntimeError("No active arrow click target")
    return {key: scalar(value) for key, value in action_inputs[0].data.items()}


def canvas_pixels(game) -> List[List[int]]:
    canvases = game.current_level.get_sprites_by_name("xytrjjbyib")
    if not canvases:
        return []
    return [[int(value) for value in row] for row in canvases[0].pixels.tolist()]


def action_enum(game_action, action_id: int):
    return getattr(game_action, f"ACTION{action_id}")


def apply_action(env, game_action, action_id: int, data: Optional[Dict[str, int | float]] = None):
    return env.step(action_enum(game_action, action_id), data or {})


def execute_level(env, game_action, write) -> Tuple[bool, Dict[str, object]]:
    level = int(env._game.level_index) + 1
    strokes = solve_strokes(env._game)
    write(
        "strokes="
        + " ".join(f"{stroke.kind[0].upper()}{stroke.position}:c{stroke.color}" for stroke in strokes)
    )

    trace: List[Dict[str, object]] = []

    def record(label: str, action_id: int, data, result) -> None:
        trace.append(
            {
                "label": label,
                "action_id": action_id,
                "data": data or {},
                "levels_completed": int(result.levels_completed),
                "brush_position": int(getattr(env._game, "xwmfgtlso", -1)),
                "color": int(getattr(env._game, "knqmgavuh", -1)),
            }
        )

    for stroke in strokes:
        if int(env._game.knqmgavuh) != stroke.color:
            data = click_data_for_swatch(env._game, stroke.color)
            result = apply_action(env, game_action, 6, data)
            record(f"C{stroke.color}", 6, data, result)
            if int(result.levels_completed) >= level:
                return True, {
                    "level": level,
                    "success": True,
                    "actions": len(trace),
                    "strokes": [asdict(stroke) for stroke in strokes],
                    "trace": trace,
                    "canvas": canvas_pixels(env._game),
                }

        path = shortest_position_path(env._game, int(env._game.xwmfgtlso), stroke.position)
        for action_char in path:
            action_id = ACTION_BY_CHAR[action_char]
            result = apply_action(env, game_action, action_id)
            record(action_char, action_id, {}, result)
            if int(result.levels_completed) >= level:
                return True, {
                    "level": level,
                    "success": True,
                    "actions": len(trace),
                    "strokes": [asdict(stroke) for stroke in strokes],
                    "trace": trace,
                    "canvas": canvas_pixels(env._game),
                }

        if stroke.kind == "basket":
            result = apply_action(env, game_action, 5)
            record("P", 5, {}, result)
        else:
            data = click_data_for_arrow(env._game)
            result = apply_action(env, game_action, 6, data)
            record("A", 6, data, result)

        if int(result.levels_completed) >= level:
            write(f"  completed L{level} at action {len(trace)}")
            return True, {
                "level": level,
                "success": True,
                "actions": len(trace),
                "strokes": [asdict(stroke) for stroke in strokes],
                "trace": trace,
                "canvas": canvas_pixels(env._game),
            }

    write(f"  failed L{level}: plan exhausted")
    return False, {
        "level": level,
        "success": False,
        "actions": len(trace),
        "strokes": [asdict(stroke) for stroke in strokes],
        "trace": trace,
        "canvas": canvas_pixels(env._game),
    }


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
        write(f"CD82 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            ok, run_info = execute_level(env, GameAction, write)
            runs.append(run_info)
            write(f"  actions={run_info['actions']}")
            labels = "".join(
                action["label"] if len(action["label"]) == 1 else f"[{action['label']}]"
                for action in run_info["trace"]
            )
            write(f"  plan={labels}")
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not ok:
                break

        success = bool(runs and runs[-1]["level"] == effective_target and runs[-1]["success"])
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "target_level": effective_target,
            "success": success,
            "runs": runs,
            "total_actions": sum(int(run["actions"]) for run in runs),
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
    parser = argparse.ArgumentParser(description="Solve CD82 by paint primitive decomposition.")
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
