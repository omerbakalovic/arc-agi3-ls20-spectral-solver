"""
V24 - centroid/path solver for ARC-AGI-3 R11L.

R11L is a click-only geometric puzzle.  Small clickable control points define
the centroid of a larger object.  Moving one control point moves that object;
the object must overlap its matching target while every intermediate centroid
avoids hazard masks.  Later levels add blank carrier objects that collect
colored fragments before being delivered to color-set targets.

The solver builds this centroid model from the local public environment source,
searches safe paths through centroid space, and replays the resulting click
coordinates against the real ARC runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import argparse
import heapq
import itertools
import json
import sys

import numpy as np

import v16_signal_runner as score_utils


GAME_ID = "r11l"
OUTPUT_DIR = Path("v24_r11l_output")
GRID = list(range(0, 64, 4))

Center = Tuple[int, int]
Centers = Tuple[Center, ...]
PlannedMove = Tuple[int, Center]


@dataclass
class SearchResult:
    path: List[PlannedMove]
    cost: int
    expansions: int
    ro_position: Center


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


def positive_colors(sprite) -> set[int]:
    return {int(value) for value in np.unique(sprite.pixels) if int(value) > 0}


def component_centers(components: Sequence[object]) -> Centers:
    return tuple((int(component.x) + 2, int(component.y) + 2) for component in components)


def ro_position(ro_sprite, centers: Centers) -> Center:
    return (
        sum(x for x, _ in centers) // len(centers) - ro_sprite.width // 2,
        sum(y for _, y in centers) // len(centers) - ro_sprite.height // 2,
    )


def ro_collides_at(ro_sprite, position: Center, target_sprite) -> bool:
    old_position = (ro_sprite.x, ro_sprite.y)
    ro_sprite.set_position(*position)
    collides = bool(ro_sprite.collides_with(target_sprite))
    ro_sprite.set_position(*old_position)
    return collides


def target_distance(ro_sprite, target_sprite, centers: Centers) -> int:
    x, y = ro_position(ro_sprite, centers)
    dx = max(
        target_sprite.x - (x + ro_sprite.width) + 1,
        x - (target_sprite.x + target_sprite.width) + 1,
        0,
    )
    dy = max(
        target_sprite.y - (y + ro_sprite.height) + 1,
        y - (target_sprite.y + target_sprite.height) + 1,
        0,
    )
    return int(dx + dy)


def centroid_hits_target(ro_sprite, target_sprite, centers: Centers) -> bool:
    return ro_collides_at(ro_sprite, ro_position(ro_sprite, centers), target_sprite)


def centroid_safe(game, ro_sprite, centers: Centers) -> bool:
    hazards = [
        sprite
        for sprite in game.current_level.get_sprites()
        if sprite.name.startswith("defgjl")
    ]
    position = ro_position(ro_sprite, centers)
    return not any(ro_collides_at(ro_sprite, position, hazard) for hazard in hazards)


def nearest_grid(value: int | float) -> int:
    return min(GRID, key=lambda candidate: abs(candidate - value))


def valid_component_center(game, component, center: Center) -> bool:
    old_selected = game.wiayqaumjug
    game.wiayqaumjug = component
    valid = not game.gabrtablhx(center[0] - 2, center[1] - 2)
    game.wiayqaumjug = old_selected
    return bool(valid)


def all_component_centers(game, group_components: Sequence[object], group_state: Centers) -> List[Center]:
    group_index = {id(component): index for index, component in enumerate(group_components)}
    centers: List[Center] = []
    for component in game.bbijaigbknc:
        index = group_index.get(id(component))
        if index is None:
            centers.append((int(component.x) + 2, int(component.y) + 2))
        else:
            centers.append(group_state[index])
    return centers


def click_hits_any_component(
    game,
    point: Center,
    group_components: Sequence[object],
    group_state: Centers,
) -> bool:
    x, y = point
    for center_x, center_y in all_component_centers(game, group_components, group_state):
        if center_x - 2 <= x < center_x + 3 and center_y - 2 <= y < center_y + 3:
            return True
    return False


def candidate_centers(
    game,
    ro_sprite,
    target_sprite,
    components: Sequence[object],
    state: Centers,
    component_index: int,
    top_k: int = 56,
) -> List[Center]:
    center_x, center_y = state[component_index]
    component_count = len(state)
    other_centers = [
        state[index]
        for index in range(component_count)
        if index != component_index
    ]
    candidates: set[Center] = set()

    base = (nearest_grid(center_x), nearest_grid(center_y))
    local_deltas = [
        (4, 0),
        (-4, 0),
        (0, 4),
        (0, -4),
        (4, 4),
        (4, -4),
        (-4, 4),
        (-4, -4),
        (8, 0),
        (-8, 0),
        (0, 8),
        (0, -8),
        (16, 0),
        (-16, 0),
        (0, 16),
        (0, -16),
    ]
    for origin_x, origin_y in [(center_x, center_y), base]:
        for dx, dy in local_deltas:
            x = nearest_grid(origin_x + dx)
            y = nearest_grid(origin_y + dy)
            if 0 <= x <= 60 and 0 <= y <= 60:
                candidates.add((x, y))

    desired_positions: List[Center] = []
    for ro_x in range(target_sprite.x - ro_sprite.width + 1, target_sprite.x + target_sprite.width):
        for ro_y in range(target_sprite.y - ro_sprite.height + 1, target_sprite.y + target_sprite.height):
            if ro_collides_at(ro_sprite, (ro_x, ro_y), target_sprite):
                desired_positions.append((ro_x, ro_y))
    desired_positions.sort(
        key=lambda pos: abs(pos[0] - (target_sprite.x + 1)) + abs(pos[1] - (target_sprite.y + 1))
    )

    offset_options = [-20, -16, -12, -8, -4, 0, 4, 8, 12, 16, 20]
    for ro_x, ro_y in desired_positions[:40]:
        required_x = component_count * (ro_x + ro_sprite.width // 2) - sum(
            x for x, _ in other_centers
        )
        required_y = component_count * (ro_y + ro_sprite.height // 2) - sum(
            y for _, y in other_centers
        )
        for snap_x in {nearest_grid(required_x + offset) for offset in offset_options}:
            for snap_y in {nearest_grid(required_y + offset) for offset in offset_options}:
                if 0 <= snap_x <= 60 and 0 <= snap_y <= 60:
                    candidates.add((snap_x, snap_y))

    scored: List[Tuple[float, int, int]] = []
    for x in GRID:
        for y in GRID:
            new_state = list(state)
            new_state[component_index] = (x, y)
            new_centers = tuple(new_state)
            if not centroid_safe(game, ro_sprite, new_centers):
                continue
            score = target_distance(ro_sprite, target_sprite, new_centers)
            score += 0.01 * (abs(x - center_x) + abs(y - center_y))
            scored.append((score, x, y))
    scored.sort()
    for _, x, y in scored[:top_k]:
        candidates.add((x, y))

    output: List[Center] = []
    component = components[component_index]
    for center in candidates:
        if center == state[component_index]:
            continue
        if not valid_component_center(game, component, center):
            continue
        if click_hits_any_component(game, center, components, state):
            continue
        new_state = list(state)
        new_state[component_index] = center
        if centroid_safe(game, ro_sprite, tuple(new_state)):
            output.append(center)
    return output


def search_controlled_group(
    game,
    group_name: str,
    target_sprite,
    max_expansions: int = 100_000,
) -> Optional[SearchResult]:
    group = game.kacotwgjcyq[group_name]
    components = group["lecfirgqbwunn"]
    ro_sprite = group["roduyfsmiznvg"]
    if ro_sprite is None or not components:
        return None

    start = component_centers(components)
    selected_index: Optional[int]
    if game.wiayqaumjug in components:
        selected_index = components.index(game.wiayqaumjug)
    else:
        selected_index = None

    queue: List[Tuple[float, int, int, Centers, Optional[int], List[PlannedMove]]] = []
    best_cost: Dict[Tuple[Centers, Optional[int]], int] = {(start, selected_index): 0}
    counter = 0
    heapq.heappush(
        queue,
        (target_distance(ro_sprite, target_sprite, start), 0, counter, start, selected_index, []),
    )
    expansions = 0

    while queue and expansions < max_expansions:
        _, cost, _, state, selected, path = heapq.heappop(queue)
        expansions += 1
        if cost != best_cost.get((state, selected)):
            continue
        if centroid_hits_target(ro_sprite, target_sprite, state) and centroid_safe(game, ro_sprite, state):
            return SearchResult(path=path, cost=cost, expansions=expansions, ro_position=ro_position(ro_sprite, state))

        for index in range(len(components)):
            for center in candidate_centers(game, ro_sprite, target_sprite, components, state, index):
                new_state = list(state)
                new_state[index] = center
                next_state = tuple(new_state)
                next_selected = index
                next_cost = cost + (1 if selected == index else 2)
                key = (next_state, next_selected)
                if next_cost >= best_cost.get(key, 999):
                    continue
                best_cost[key] = next_cost
                counter += 1
                heuristic = target_distance(ro_sprite, target_sprite, next_state) / 2
                heapq.heappush(
                    queue,
                    (
                        next_cost + heuristic,
                        next_cost,
                        counter,
                        next_state,
                        next_selected,
                        path + [(index, center)],
                    ),
                )
    return None


def select_point_for_component(game, component) -> Center:
    candidates: List[Tuple[int, int, int, int]] = []
    for x in GRID:
        for y in GRID:
            if component.x <= x < component.x + component.width and component.y <= y < component.y + component.height:
                hits = [
                    other
                    for other in game.bbijaigbknc
                    if other.x <= x < other.x + other.width and other.y <= y < other.y + other.height
                ]
                distance = abs(x - (component.x + 2)) + abs(y - (component.y + 2))
                candidates.append((len(hits), distance, x, y))
    if not candidates:
        return (int(component.x) + 2, int(component.y) + 2)
    candidates.sort()
    return (candidates[0][2], candidates[0][3])


def snapshot(game) -> Dict[str, object]:
    groups = {}
    for name, data in sorted(game.kacotwgjcyq.items()):
        ro_sprite = data["roduyfsmiznvg"]
        target = data["gosubdcyegamj"]
        components = data["lecfirgqbwunn"]
        groups[name] = {
            "ro": [int(ro_sprite.x), int(ro_sprite.y)] if ro_sprite is not None else None,
            "target": [int(target.x), int(target.y)] if target is not None else None,
            "collides_target": bool(ro_sprite and target and ro_sprite.collides_with(target)),
            "components": [[int(component.x), int(component.y)] for component in components],
            "colors": sorted(positive_colors(ro_sprite)) if ro_sprite is not None else [],
        }
    return {
        "level_index": int(game.level_index) + 1,
        "selected": getattr(game.wiayqaumjug, "name", None),
        "groups": groups,
        "collected": {key: list(value) for key, value in game.bulmhgivatv.items()},
        "remaining_items": [sprite.name for sprite in game.owuypsqbino],
    }


def apply_planned_move(env, game_action, group_name: str, component_index: int, center: Center, trace: List[Dict[str, object]]):
    game = env._game
    component = game.kacotwgjcyq[group_name]["lecfirgqbwunn"][component_index]
    if game.wiayqaumjug is not component:
        x, y = select_point_for_component(game, component)
        result = env.step(getattr(game_action, "ACTION6"), {"x": x, "y": y})
        trace.append(
            {
                "label": f"S:{group_name}:{component_index}",
                "action_id": 6,
                "data": {"x": x, "y": y},
                "levels_completed": int(result.levels_completed),
                "snapshot": snapshot(game),
            }
        )
    result = env.step(getattr(game_action, "ACTION6"), {"x": center[0], "y": center[1]})
    trace.append(
        {
            "label": f"M:{group_name}:{component_index}",
            "action_id": 6,
            "data": {"x": center[0], "y": center[1]},
            "levels_completed": int(result.levels_completed),
            "snapshot": snapshot(game),
        }
    )
    return result


def direct_target_groups(game) -> List[str]:
    names: List[str] = []
    for name, data in sorted(game.kacotwgjcyq.items()):
        if "dirwzt" in name:
            continue
        if data["roduyfsmiznvg"] is not None and data["gosubdcyegamj"] is not None:
            names.append(name)
    return names


def collection_targets(game) -> List[str]:
    names: List[str] = []
    for name, data in sorted(game.kacotwgjcyq.items()):
        if "dirwzt" in name:
            continue
        if data["roduyfsmiznvg"] is None and data["gosubdcyegamj"] is not None:
            names.append(name)
    return names


def carrier_groups(game) -> List[str]:
    names: List[str] = []
    for name, data in sorted(game.kacotwgjcyq.items()):
        if data["roduyfsmiznvg"] is not None and data["gosubdcyegamj"] is None and data["lecfirgqbwunn"]:
            names.append(name)
    return names


def group_solved(game, group_name: str) -> bool:
    data = game.kacotwgjcyq[group_name]
    ro_sprite = data["roduyfsmiznvg"]
    target = data["gosubdcyegamj"]
    return bool(ro_sprite is not None and target is not None and ro_sprite.collides_with(target))


def execute_path(env, game_action, group_name: str, target_sprite, trace: List[Dict[str, object]], write) -> None:
    result = search_controlled_group(env._game, group_name, target_sprite)
    if result is None:
        raise RuntimeError(f"No centroid path for {group_name} -> {target_sprite.name}")
    write(
        f"  {group_name} -> {target_sprite.name} "
        f"cost={result.cost} exp={result.expansions} ro={result.ro_position}"
    )
    for component_index, center in result.path:
        apply_planned_move(env, game_action, group_name, component_index, center, trace)


def solve_direct_level(env, game_action, level: int, trace: List[Dict[str, object]], write) -> None:
    while int(env._game.level_index) + 1 == level:
        unsolved = [name for name in direct_target_groups(env._game) if not group_solved(env._game, name)]
        if not unsolved:
            return
        group_name = unsolved[0]
        target = env._game.kacotwgjcyq[group_name]["gosubdcyegamj"]
        execute_path(env, game_action, group_name, target, trace, write)


def rough_route_cost(game, carrier_name: str, item_sprites: Sequence[object], target_sprite) -> int:
    carrier = game.kacotwgjcyq[carrier_name]["roduyfsmiznvg"]
    if carrier is None:
        return 10_000
    x, y = carrier.x, carrier.y
    total = 0
    for item in item_sprites:
        total += abs(x - item.x) + abs(y - item.y)
        x, y = item.x, item.y
    total += abs(x - target_sprite.x) + abs(y - target_sprite.y)
    return total


def choose_collection_assignment(game) -> List[Tuple[str, str, List[object]]]:
    targets = collection_targets(game)
    carriers = carrier_groups(game)
    if len(targets) > len(carriers):
        raise RuntimeError("Not enough carrier groups for collection targets")

    target_items: Dict[str, List[object]] = {}
    for target_name in targets:
        target_colors = positive_colors(game.kacotwgjcyq[target_name]["gosubdcyegamj"])
        items = [
            item
            for item in game.owuypsqbino
            if positive_colors(item) and positive_colors(item).issubset(target_colors)
        ]
        covered = set().union(*(positive_colors(item) for item in items)) if items else set()
        if covered != target_colors:
            raise RuntimeError(f"Could not cover target colors for {target_name}: {target_colors}")
        target_items[target_name] = items

    best: Optional[Tuple[int, List[Tuple[str, str, List[object]]]]] = None
    for carrier_order in itertools.permutations(carriers, len(targets)):
        assignment: List[Tuple[str, str, List[object]]] = []
        score = 0
        for carrier_name, target_name in zip(carrier_order, targets):
            target = game.kacotwgjcyq[target_name]["gosubdcyegamj"]
            remaining = list(target_items[target_name])
            ordered_items: List[object] = []
            carrier = game.kacotwgjcyq[carrier_name]["roduyfsmiznvg"]
            x, y = carrier.x, carrier.y
            while remaining:
                next_item = min(remaining, key=lambda item: abs(x - item.x) + abs(y - item.y))
                ordered_items.append(next_item)
                remaining.remove(next_item)
                x, y = next_item.x, next_item.y
            score += rough_route_cost(game, carrier_name, ordered_items, target)
            assignment.append((carrier_name, target_name, ordered_items))
        if best is None or score < best[0]:
            best = (score, assignment)
    if best is None:
        return []
    return best[1]


def solve_collection_level(env, game_action, level: int, trace: List[Dict[str, object]], write) -> None:
    assignments = choose_collection_assignment(env._game)
    for carrier_name, target_name, items in assignments:
        if int(env._game.level_index) + 1 != level:
            break
        write(
            f"  carrier {carrier_name} collects {[item.name for item in items]} "
            f"for {target_name}"
        )
        for item in list(items):
            live_items = [sprite for sprite in env._game.owuypsqbino if sprite.name == item.name]
            if not live_items:
                continue
            execute_path(env, game_action, carrier_name, live_items[0], trace, write)
        target = env._game.kacotwgjcyq[target_name]["gosubdcyegamj"]
        execute_path(env, game_action, carrier_name, target, trace, write)


def solve_current_level(env, game_action, level: int, trace: List[Dict[str, object]], write) -> bool:
    start_completed = int(level) - 1
    if direct_target_groups(env._game):
        solve_direct_level(env, game_action, level, trace, write)
    if int(env._game.level_index) + 1 == level and collection_targets(env._game):
        solve_collection_level(env, game_action, level, trace, write)
    return int(trace[-1]["levels_completed"]) >= level if trace else start_completed >= level


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
        write(f"R11L target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            trace: List[Dict[str, object]] = []
            ok = solve_current_level(env, GameAction, level, trace, write)
            labels = " ".join(
                f"{entry['label']}@({entry['data']['x']},{entry['data']['y']})"
                for entry in trace
            )
            write(f"  actions={len(trace)}")
            write(f"  plan={labels}")
            runs.append(
                {
                    "level": level,
                    "success": ok,
                    "actions": len(trace),
                    "trace": trace,
                }
            )
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
    parser = argparse.ArgumentParser(description="Solve R11L by centroid path search.")
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
