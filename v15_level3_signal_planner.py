"""
V15 - Level 3 signal/graph planner.

This is the first pass at turning the successful hand plan from v14.22 into
an actual planner.  The level is treated as a small labelled transition graph:

    node = (player_cell, shape_idx, color_idx, rotation_idx, energy, collected)

Normal movement follows the 5px grid.  Special visual objects become operators:
    rhsxkxzdjz  -> rotation +90
    soyhouuebz  -> color cycle +1
    ttfwljgohq  -> shape cycle +1
    npxgalaybz  -> energy reset
    *_r/_l/_t/_b with tag gbvqrjtaqo -> pusher/teleport operator

The planner parses Level 3 from environment_files/ls20/9607627b/ls20.py,
searches the augmented state graph, executes the resulting plan, and writes
its evidence to v15_level3_signal_output/log.txt.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import json
import os
import re
import sys

import numpy as np


GAME_ID = "ls20"
SRC_PATH = Path("environment_files/ls20/9607627b/ls20.py")
OUTPUT_DIR = Path("v15_level3_signal_output")

CELL = 5
ROWS = range(0, 56, CELL)
COLS = range(4, 60, CELL)
DELTA = {"U": (-CELL, 0), "D": (CELL, 0), "L": (0, -CELL), "R": (0, CELL)}
DIR_TO_VEC_XY = {"r": (1, 0), "l": (-1, 0), "t": (0, -1), "b": (0, 1)}
DIR_TO_ACTION = {"r": "R", "l": "L", "t": "U", "b": "D"}

arc_agi = None
GameAction = None


def ensure_arc_runtime():
    global arc_agi, GameAction
    if arc_agi is None or GameAction is None:
        import arc_agi as _arc_agi
        from arcengine import GameAction as _GameAction

        arc_agi = _arc_agi
        GameAction = _GameAction
    return arc_agi, GameAction


def action_map():
    _, game_action = ensure_arc_runtime()
    return {
        "U": game_action.ACTION1,
        "D": game_action.ACTION2,
        "L": game_action.ACTION3,
        "R": game_action.ACTION4,
    }


@dataclass(frozen=True)
class Placement:
    name: str
    x: int
    y: int


@dataclass(frozen=True)
class SpriteInfo:
    width: int
    height: int
    pixels: Tuple[Tuple[int, ...], ...]
    tags: Set[str]


@dataclass(frozen=True)
class MovingEffect:
    name: str
    tag: str
    start_x: int
    start_y: int
    mask_name: str
    mask_x: int
    mask_y: int
    mask_pixels: Tuple[Tuple[int, ...], ...]


@dataclass(frozen=True)
class ExitGoal:
    cell: Tuple[int, int]
    shape: int
    color_idx: int
    rot_idx: int


@dataclass(frozen=True)
class Pusher:
    name: str
    x: int
    y: int
    direction: str
    action: str
    delta: Tuple[int, int]  # row, col delta applied to the player
    contacts: Tuple[Tuple[int, int], ...]


@dataclass
class LevelModel:
    walkable: Set[Tuple[int, int]]
    start_cell: Tuple[int, int]
    exit_cell: Tuple[int, int]
    goals: Tuple[ExitGoal, ...]
    step_counter: int
    step_decrement: int
    shape_count: int
    start_shape: int
    goal_shape: int
    color_order: List[int]
    start_color_idx: int
    goal_color_idx: int
    rotations: List[int]
    start_rot_idx: int
    goal_rot_idx: int
    shape_triggers: Set[Tuple[int, int]]
    color_triggers: Set[Tuple[int, int]]
    rotation_triggers: Set[Tuple[int, int]]
    collectibles: Set[Tuple[int, int]]
    pushers: List[Pusher]
    moving_effects: Tuple[MovingEffect, ...]
    start_movers: Tuple[Tuple[int, int, int], ...]
    seed_moves: int = 2


def log_sink():
    OUTPUT_DIR.mkdir(exist_ok=True)
    lines: List[str] = []

    def write(msg: str = "") -> None:
        s = str(msg)
        print(s)
        lines.append(s)
        sys.stdout.flush()

    def flush() -> None:
        (OUTPUT_DIR / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    return write, flush


def parse_constants(src: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for name, value in re.findall(r"^([a-zA-Z_]\w*)\s*=\s*(-?\d+)\s*$", src, re.M):
        out[name] = int(value)
    return out


def parse_list_from_assignment(src: str, attr: str, constants: Dict[str, int]) -> List[int]:
    m = re.search(rf"self\.{re.escape(attr)}\s*=\s*\[([^\]]+)\]", src)
    if not m:
        return []
    values = []
    for token in m.group(1).split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token) if token.lstrip("-").isdigit() else constants[token])
    return values


def parse_sprite_info(src: str) -> Dict[str, SpriteInfo]:
    info_by_name: Dict[str, SpriteInfo] = {}
    pattern = re.compile(r'"([^"]+)":\s*Sprite\((.*?)\n    \),', re.S)
    for name, body in pattern.findall(src):
        tags: Set[str] = set()
        m = re.search(r"tags=\[([^\]]*)\]", body, re.S)
        if m:
            tags.update(re.findall(r'"([^"]+)"', m.group(1)))
        pixels: List[Tuple[int, ...]] = []
        p = re.search(r"pixels=\s*\[(.*?)\]\s*,\s*name=", body, re.S)
        if p:
            for row in re.findall(r"\[([^\]]*)\]", p.group(1)):
                values = tuple(int(v) for v in re.findall(r"-?\d+", row))
                if values:
                    pixels.append(values)
        width = max((len(row) for row in pixels), default=CELL)
        height = len(pixels) if pixels else CELL
        info_by_name[name] = SpriteInfo(
            width=width,
            height=height,
            pixels=tuple(pixels),
            tags=tags,
        )
    return info_by_name


def parse_sprite_tags(src: str) -> Dict[str, Set[str]]:
    info_by_name = parse_sprite_info(src)
    return {name: info.tags for name, info in info_by_name.items()}


def level_block(src: str, level_number: int) -> str:
    start = re.search(rf"^\s*# Level {level_number}\s*$", src, re.M)
    if not start:
        raise ValueError(f"Cannot find Level {level_number}")
    end = re.search(r"^\s*# Level \d+\s*$", src[start.end() :], re.M)
    return src[start.end() : start.end() + end.start()] if end else src[start.end() :]


def max_level_number(src: Optional[str] = None) -> int:
    text = SRC_PATH.read_text(encoding="utf-8") if src is None else src
    levels = [int(n) for n in re.findall(r"^\s*# Level (\d+)\s*$", text, re.M)]
    return max(levels) if levels else 0


def parse_level_data(block: str) -> Dict[str, object]:
    m = re.search(r"data=\{(.*?)\n\s*\}", block, re.S)
    if not m:
        return {}
    data: Dict[str, object] = {}
    for key, value in re.findall(r'"([^"]+)":\s*(\[[^\]]*\]|-?\d+|True|False)', m.group(1)):
        value = value.strip()
        if value in ("True", "False"):
            continue
        if value.startswith("["):
            data[key] = [int(v) for v in re.findall(r"-?\d+", value)]
            continue
        if value.lstrip("-").isdigit():
            data[key] = int(value)
    return data


def parse_placements(block: str) -> List[Placement]:
    out = []
    pat = re.compile(r'sprites\["([^"]+)"\]\.clone\(\).*?\.set_position\((\d+),\s*(\d+)\)')
    for name, x, y in pat.findall(block):
        out.append(Placement(name=name, x=int(x), y=int(y)))
    return out


def rects_overlap(ax: int, ay: int, aw: int, ah: int, bx: int, by: int, bw: int, bh: int) -> bool:
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def cell_overlaps_sprite(cell: Tuple[int, int], p: Placement) -> bool:
    row, col = cell
    return rects_overlap(col, row, CELL, CELL, p.x, p.y, CELL, CELL)


def cell_for_placement(p: Placement, walkable: Set[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    hits = [cell for cell in walkable if cell_overlaps_sprite(cell, p)]
    if not hits:
        return None
    hits.sort(key=lambda c: abs(c[0] - p.y) + abs(c[1] - p.x))
    return hits[0]


def build_walkable(walls: Sequence[Placement]) -> Set[Tuple[int, int]]:
    walkable: Set[Tuple[int, int]] = set()
    for row in ROWS:
        for col in COLS:
            blocked = any(rects_overlap(col, row, CELL, CELL, w.x, w.y, CELL, CELL) for w in walls)
            if not blocked:
                walkable.add((row, col))
    return walkable


def data_sequence(data: Dict[str, object], key: str, fallback: int, count: int) -> List[int]:
    value = data.get(key, fallback)
    if isinstance(value, list):
        if len(value) >= count:
            return [int(v) for v in value[:count]]
        if value:
            return [int(v) for v in value] + [int(value[-1])] * (count - len(value))
        return [fallback] * count
    return [int(value)] * count


def normalize_goal_shape(data: Dict[str, object]) -> int:
    value = data.get("kvynsvxbpi", data.get("GoalShape", data.get("StartShape", 0)))
    if isinstance(value, list):
        return int(value[0]) if value else int(data.get("StartShape", 0))
    return int(value)


def pusher_delta(p: Placement, obstacles_xy: Set[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    direction = p.name[-1]
    if direction not in DIR_TO_VEC_XY:
        return None
    dx, dy = DIR_TO_VEC_XY[direction]
    wall_x = p.x + dx
    wall_y = p.y + dy
    hit_index = None
    for i in range(1, 12):
        test = (wall_x + dx * CELL * i, wall_y + dy * CELL * i)
        if test in obstacles_xy:
            hit_index = i
            break
    if hit_index is None:
        return None
    push_cells = max(0, hit_index - 1)
    return (dy * CELL * push_cells, dx * CELL * push_cells)


def placement_key(p: Placement, tag: str) -> Tuple[str, int, int, str]:
    return (p.name, p.x, p.y, tag)


def sprite_allows_position(effect: MovingEffect, x: int, y: int) -> bool:
    rel_x = x - effect.mask_x
    rel_y = y - effect.mask_y
    if rel_y < 0 or rel_y >= len(effect.mask_pixels):
        return False
    row = effect.mask_pixels[rel_y]
    if rel_x < 0 or rel_x >= len(row):
        return False
    return row[rel_x] >= 0


def mover_vec(direction: int) -> Tuple[int, int]:
    if direction == 0:
        return (0, 1)
    if direction == 1:
        return (1, 0)
    if direction == 2:
        return (0, -1)
    return (-1, 0)


def advance_one_mover(effect: MovingEffect, mover: Tuple[int, int, int]) -> Tuple[int, int, int]:
    x, y, direction = mover
    for candidate in (direction, (direction - 1) % 4, (direction + 1) % 4, (direction + 2) % 4):
        dx, dy = mover_vec(candidate)
        nx = x + dx * CELL
        ny = y + dy * CELL
        if sprite_allows_position(effect, nx, ny):
            return (nx, ny, candidate)
    return mover


def advance_movers(
    effects: Sequence[MovingEffect],
    movers: Tuple[Tuple[int, int, int], ...],
) -> Tuple[Tuple[int, int, int], ...]:
    if not effects:
        return movers
    return tuple(advance_one_mover(effect, mover) for effect, mover in zip(effects, movers))


def mover_cycle_positions(effect: MovingEffect) -> Set[Tuple[int, int]]:
    state = (effect.start_x, effect.start_y, 0)
    seen: Set[Tuple[int, int, int]] = set()
    positions: Set[Tuple[int, int]] = set()
    for _ in range(256):
        if state in seen:
            break
        seen.add(state)
        positions.add((state[1], state[0]))
        state = advance_one_mover(effect, state)
    return positions


def moving_effect_cells(
    model: LevelModel,
    movers: Tuple[Tuple[int, int, int], ...],
) -> Dict[Tuple[int, int], List[str]]:
    cells: Dict[Tuple[int, int], List[str]] = {}
    for effect, mover in zip(model.moving_effects, movers):
        x, y, _ = mover
        cells.setdefault((y, x), []).append(effect.tag)
    return cells


def effect_tags_at(
    model: LevelModel,
    pos: Tuple[int, int],
    movers: Tuple[Tuple[int, int, int], ...],
) -> List[str]:
    tags: List[str] = []
    if pos in model.shape_triggers:
        tags.append("ttfwljgohq")
    if pos in model.color_triggers:
        tags.append("soyhouuebz")
    if pos in model.rotation_triggers:
        tags.append("rhsxkxzdjz")
    tags.extend(moving_effect_cells(model, movers).get(pos, []))
    return tags


def discover_moving_effects(
    placements: Sequence[Placement],
    sprite_info: Dict[str, SpriteInfo],
) -> Tuple[Tuple[MovingEffect, ...], Set[Tuple[str, int, int, str]]]:
    trigger_tags = ("ttfwljgohq", "soyhouuebz", "rhsxkxzdjz")
    masks = [p for p in placements if "xfmluydglp" in sprite_info.get(p.name, SpriteInfo(CELL, CELL, (), set())).tags]
    moving: List[MovingEffect] = []
    moving_keys: Set[Tuple[str, int, int, str]] = set()
    for mask in masks:
        mask_info = sprite_info[mask.name]
        for trigger in placements:
            trigger_info = sprite_info.get(trigger.name)
            if trigger_info is None:
                continue
            tag = next((t for t in trigger_tags if t in trigger_info.tags), None)
            if tag is None:
                continue
            if not rects_overlap(
                mask.x,
                mask.y,
                mask_info.width,
                mask_info.height,
                trigger.x,
                trigger.y,
                trigger_info.width,
                trigger_info.height,
            ):
                continue
            moving.append(
                MovingEffect(
                    name=trigger.name,
                    tag=tag,
                    start_x=trigger.x,
                    start_y=trigger.y,
                    mask_name=mask.name,
                    mask_x=mask.x,
                    mask_y=mask.y,
                    mask_pixels=mask_info.pixels,
                )
            )
            moving_keys.add(placement_key(trigger, tag))
    return tuple(moving), moving_keys


def build_model(level_number: int = 3, seed_moves: int = 2) -> LevelModel:
    src = SRC_PATH.read_text(encoding="utf-8")
    constants = parse_constants(src)
    color_order = parse_list_from_assignment(src, "tnkekoeuk", constants) or [12, 9, 14, 8]
    rotations = parse_list_from_assignment(src, "dhksvilbb", constants) or [0, 90, 180, 270]
    sprite_info = parse_sprite_info(src)
    tags_by_name = {name: info.tags for name, info in sprite_info.items()}
    block = level_block(src, level_number)
    data = parse_level_data(block)
    placements = parse_placements(block)
    moving_effects, moving_keys = discover_moving_effects(placements, sprite_info)

    walls = [p for p in placements if "ihdgageizm" in tags_by_name.get(p.name, set())]
    exits = [p for p in placements if "rjlbuycveu" in tags_by_name.get(p.name, set())]
    players = [p for p in placements if "sfqyzhzkij" in tags_by_name.get(p.name, set())]
    if not exits or not players:
        raise ValueError("Level is missing player or exit placement")

    walkable = build_walkable(walls)
    exit_cells: List[Tuple[int, int]] = []
    for exit_placement in exits:
        exit_cell = cell_for_placement(exit_placement, walkable)
        if exit_cell is None:
            exit_cell = (exit_placement.y, exit_placement.x)
        exit_cells.append(exit_cell)
        walkable.add(exit_cell)
    primary_exit_cell = exit_cells[0]

    raw_start = (players[0].y, players[0].x)
    start_cell = (raw_start[0] - seed_moves * CELL, raw_start[1])
    walkable.add(start_cell)

    def cells_for_tag(tag: str) -> Set[Tuple[int, int]]:
        cells = set()
        for p in placements:
            if tag not in tags_by_name.get(p.name, set()):
                continue
            if placement_key(p, tag) in moving_keys:
                continue
            cell = cell_for_placement(p, walkable)
            if cell is not None:
                cells.add(cell)
        return cells

    shape_triggers = cells_for_tag("ttfwljgohq")
    color_triggers = cells_for_tag("soyhouuebz")
    rotation_triggers = cells_for_tag("rhsxkxzdjz")
    collectibles = cells_for_tag("npxgalaybz")
    walkable |= shape_triggers | color_triggers | rotation_triggers | collectibles
    for effect in moving_effects:
        walkable |= mover_cycle_positions(effect)

    obstacle_xy = {(p.x, p.y) for p in walls + exits}
    pushers: List[Pusher] = []
    for p in placements:
        if "gbvqrjtaqo" not in tags_by_name.get(p.name, set()):
            continue
        direction = p.name[-1]
        delta = pusher_delta(p, obstacle_xy)
        if direction not in DIR_TO_ACTION or delta is None or delta == (0, 0):
            continue
        contacts = tuple(sorted(cell for cell in walkable if cell_overlaps_sprite(cell, p)))
        if contacts:
            pushers.append(
                Pusher(
                    name=p.name,
                    x=p.x,
                    y=p.y,
                    direction=direction,
                    action=DIR_TO_ACTION[direction],
                    delta=delta,
                    contacts=contacts,
                )
            )

    step_counter = int(data.get("StepCounter", 0))
    step_decrement = int(data.get("StepsDecrement", 2))
    start_color = int(data.get("StartColor", color_order[0]))
    start_rot = int(data.get("StartRotation", rotations[0]))
    start_shape = int(data.get("StartShape", 0))
    goal_shapes = data_sequence(data, "kvynsvxbpi", int(data.get("GoalShape", start_shape)), len(exit_cells))
    goal_colors = data_sequence(data, "GoalColor", start_color, len(exit_cells))
    goal_rots = data_sequence(data, "GoalRotation", start_rot, len(exit_cells))
    goals = tuple(
        ExitGoal(
            cell=cell,
            shape=goal_shapes[i],
            color_idx=color_order.index(goal_colors[i]),
            rot_idx=rotations.index(goal_rots[i]),
        )
        for i, cell in enumerate(exit_cells)
    )
    goal_shape = goals[0].shape
    goal_color_idx = goals[0].color_idx
    goal_rot_idx = goals[0].rot_idx
    start_movers = tuple((effect.start_x, effect.start_y, 0) for effect in moving_effects)
    for _ in range(seed_moves):
        start_movers = advance_movers(moving_effects, start_movers)

    return LevelModel(
        walkable=walkable,
        start_cell=start_cell,
        exit_cell=primary_exit_cell,
        goals=goals,
        step_counter=step_counter,
        step_decrement=step_decrement,
        shape_count=6,
        start_shape=start_shape,
        goal_shape=goal_shape,
        color_order=color_order,
        start_color_idx=color_order.index(start_color),
        goal_color_idx=goal_color_idx,
        rotations=rotations,
        start_rot_idx=rotations.index(start_rot),
        goal_rot_idx=goal_rot_idx,
        shape_triggers=shape_triggers,
        color_triggers=color_triggers,
        rotation_triggers=rotation_triggers,
        collectibles=collectibles,
        pushers=pushers,
        moving_effects=moving_effects,
        start_movers=start_movers,
        seed_moves=seed_moves,
    )


State = Tuple[
    Tuple[int, int],
    int,
    int,
    int,
    int,
    frozenset,
    frozenset,
    Tuple[Tuple[int, int, int], ...],
]


def is_goal(model: LevelModel, state: State) -> bool:
    _, _, _, _, _, _, completed_goals, _ = state
    return len(completed_goals) == len(model.goals)


def is_exit_cell(model: LevelModel, pos: Tuple[int, int]) -> bool:
    return any(pos == goal.cell for goal in model.goals)


def matching_exit_goal(
    model: LevelModel,
    pos: Tuple[int, int],
    shape: int,
    color: int,
    rot: int,
    completed_goals: frozenset,
) -> Optional[int]:
    for i, goal in enumerate(model.goals):
        if i in completed_goals:
            continue
        if pos == goal.cell and shape == goal.shape and color == goal.color_idx and rot == goal.rot_idx:
            return i
    return None


def apply_tile_effects(
    model: LevelModel,
    pos: Tuple[int, int],
    shape: int,
    color: int,
    rot: int,
    movers: Tuple[Tuple[int, int, int], ...],
):
    tags = effect_tags_at(model, pos, movers)
    if "ttfwljgohq" in tags:
        shape = (shape + 1) % model.shape_count
    if "soyhouuebz" in tags:
        color = (color + 1) % len(model.color_order)
    if "rhsxkxzdjz" in tags:
        rot = (rot + 1) % len(model.rotations)
    return shape, color, rot


def pusher_from(model: LevelModel, pos: Tuple[int, int], action: str) -> Optional[Pusher]:
    for p in model.pushers:
        if action == p.action and pos in p.contacts:
            return p
    return None


def pusher_at(model: LevelModel, pos: Tuple[int, int]) -> Optional[Pusher]:
    for p in model.pushers:
        if pos in p.contacts:
            return p
    return None


def successors(model: LevelModel, state: State) -> Iterable[Tuple[str, State, str]]:
    pos, shape, color, rot, energy, collected, completed_goals, movers = state
    active_pusher = pusher_at(model, pos)
    for action, (dr, dc) in DELTA.items():
        push = pusher_from(model, pos, action)
        event = ""
        new_completed_goals = completed_goals
        if push is not None:
            new_pos = (pos[0] + push.delta[0], pos[1] + push.delta[1])
            new_movers = movers
            event = f"pusher:{push.name}"
        else:
            if active_pusher is not None:
                continue
            new_movers = advance_movers(model.moving_effects, movers)
            new_pos = (pos[0] + dr, pos[1] + dc)
            if new_pos not in model.walkable:
                continue

        if is_exit_cell(model, new_pos):
            if any(i in completed_goals and goal.cell == new_pos for i, goal in enumerate(model.goals)):
                pass
            else:
                matched_goal = matching_exit_goal(model, new_pos, shape, color, rot, completed_goals)
                if matched_goal is None:
                    continue
                new_completed_goals = frozenset(set(completed_goals) | {matched_goal})
                event = "exit" if not event else event + "+exit"

        new_shape, new_color, new_rot = apply_tile_effects(model, new_pos, shape, color, rot, new_movers)
        new_energy = energy - model.step_decrement
        new_collected = collected
        if new_pos in model.collectibles and new_pos not in collected:
            new_energy = model.step_counter
            new_collected = frozenset(set(collected) | {new_pos})
            event = "collectible" if not event else event + "+collectible"

        new_state: State = (
            new_pos,
            new_shape,
            new_color,
            new_rot,
            new_energy,
            new_collected,
            new_completed_goals,
            new_movers,
        )
        if is_goal(model, new_state):
            yield action, new_state, event or "exit"
        elif new_energy >= 0:
            yield action, new_state, event


def initial_state(model: LevelModel) -> State:
    start_energy = model.step_counter - model.seed_moves * model.step_decrement
    return (
        model.start_cell,
        model.start_shape,
        model.start_color_idx,
        model.start_rot_idx,
        start_energy,
        frozenset(),
        frozenset(),
        model.start_movers,
    )


def search_until(
    model: LevelModel,
    start: State,
    stop,
) -> Tuple[List[str], List[Tuple[int, str, State, str]], State]:
    pq = [(0, 0, start)]
    seq = 1
    best_cost: Dict[State, int] = {start: 0}
    parent: Dict[State, Tuple[State, str, str]] = {}

    while pq:
        cost, _, state = heappop(pq)
        if cost != best_cost.get(state):
            continue
        if stop(state):
            actions: List[str] = []
            trace: List[Tuple[int, str, State, str]] = []
            cur = state
            while cur in parent:
                prev, action, event = parent[cur]
                actions.append(action)
                trace.append((len(actions), action, cur, event))
                cur = prev
            actions.reverse()
            trace.reverse()
            trace = [(i + 1, action, st, event) for i, (_, action, st, event) in enumerate(trace)]
            return actions, trace, state

        for action, nxt, event in successors(model, state):
            ncost = cost + 1
            if ncost < best_cost.get(nxt, 10**9):
                best_cost[nxt] = ncost
                parent[nxt] = (state, action, event)
                heappush(pq, (ncost, seq, nxt))
                seq += 1

    raise RuntimeError("No plan found")


def find_plan(model: LevelModel) -> Tuple[List[str], List[Tuple[int, str, State, str]]]:
    start = initial_state(model)
    if len(model.goals) <= 1:
        actions, trace, _ = search_until(model, start, lambda state: is_goal(model, state))
        return actions, trace

    actions: List[str] = []
    trace: List[Tuple[int, str, State, str]] = []
    state = start
    while not is_goal(model, state):
        completed_before = len(state[6])
        stage_actions, stage_trace, state = search_until(
            model,
            state,
            lambda candidate, n=completed_before: len(candidate[6]) > n,
        )
        offset = len(actions)
        actions.extend(stage_actions)
        trace.extend((offset + step, action, st, event) for step, action, st, event in stage_trace)
    return actions, trace


def detect_player(frame: Optional[np.ndarray], color: int = 12) -> Optional[Tuple[int, int]]:
    if frame is None:
        return None
    mask = frame[:55, :] == color
    if not np.any(mask):
        return None
    h, width = mask.shape
    for y in range(h - 1):
        for x in range(width - 4):
            if mask[y : y + 2, x : x + 5].all():
                return (y, x)
    return None


def do_l1(env):
    _, game_action = ensure_arc_runtime()
    env.step(game_action.ACTION1)
    env.step(game_action.ACTION1)
    route = [game_action.ACTION1] * 2
    route += [game_action.ACTION3] * 3
    route += [game_action.ACTION2]
    route += [game_action.ACTION1] * 2
    route += [game_action.ACTION4] * 3
    route += [game_action.ACTION1] * 3
    result = None
    for action in route:
        result = env.step(action)
        if int(result.levels_completed) >= 1:
            return result
    return result


def solve_l2(env):
    _, game_action = ensure_arc_runtime()
    act = action_map()
    plan = list("RUUUUURRDRDDDDDDDLLRURUDUUUUUUULLLLLLDLDDDDD")
    env.step(game_action.ACTION1)
    env.step(game_action.ACTION1)
    result = None
    for action in plan:
        result = env.step(act[action])
        if not result.frame:
            return result
        if int(result.levels_completed) >= 2:
            return result
    return result


def execute_plan(plan: Sequence[str], write) -> Tuple[bool, Optional[int]]:
    arc_module, game_action = ensure_arc_runtime()
    act = action_map()
    arc = arc_module.Arcade()
    env = arc.make(GAME_ID, render_mode=None)
    result = do_l1(env)
    write(f"L1 lvl={result.levels_completed}")
    result = solve_l2(env)
    write(f"L2 lvl={result.levels_completed}")
    if int(result.levels_completed) < 2:
        return False, None

    env.step(game_action.ACTION1)
    result = env.step(game_action.ACTION1)
    frame = np.array(result.frame[0])
    write(f"L3 seed pos={detect_player(frame)} lvl={result.levels_completed}")

    base_lvl = int(result.levels_completed)
    for i, action in enumerate(plan, 1):
        result = env.step(act[action])
        if not result.frame:
            write(f"  [{i}] {action} LIFE LOST")
            return False, None
        frame = np.array(result.frame[0])
        pos = detect_player(frame)
        lvl = int(result.levels_completed)
        write(f"  [{i:02d}] {action} pos={pos} lvl={lvl}")
        if lvl > base_lvl:
            write(f"*** LEVEL 3 SOLVED at planned step {i} ***")
            return True, i
    return int(result.levels_completed) > base_lvl, None


@dataclass
class ExecutionResult:
    executed: bool
    success: Optional[bool]
    solved_step: Optional[int] = None
    reason: str = ""


def main() -> None:
    write, flush = log_sink()
    model = build_model(level_number=3)
    plan, trace = find_plan(model)

    write("=== Signal model ===")
    write(f"walkable={len(model.walkable)} start={model.start_cell} exit={model.exit_cell}")
    write(
        "state "
        f"shape {model.start_shape}->{model.goal_shape}, "
        f"color {model.color_order[model.start_color_idx]}->{model.color_order[model.goal_color_idx]}, "
        f"rot {model.rotations[model.start_rot_idx]}->{model.rotations[model.goal_rot_idx]}"
    )
    if len(model.goals) > 1:
        goals = [
            f"{goal.cell}:s{goal.shape}/c{model.color_order[goal.color_idx]}/r{model.rotations[goal.rot_idx]}"
            for goal in model.goals
        ]
        write(f"goals={goals}")
    write(f"collectibles={sorted(model.collectibles)}")
    for effect in model.moving_effects:
        write(
            f"moving {effect.tag}:{effect.name}@({effect.start_x},{effect.start_y}) "
            f"mask={effect.mask_name}@({effect.mask_x},{effect.mask_y})"
        )
    for p in model.pushers:
        write(f"pusher {p.name}@({p.x},{p.y}) action={p.action} delta={p.delta} contacts={list(p.contacts)}")

    write(f"\nPlan ({len(plan)} moves): {''.join(plan)}")
    for step, action, state, event in trace:
        pos, shape, color, rot, energy, collected, completed_goals, movers = state
        label = event or ""
        tags = effect_tags_at(model, pos, movers)
        if "ttfwljgohq" in tags:
            label = (label + " shape").strip()
        if "soyhouuebz" in tags:
            label = (label + " color").strip()
        if "rhsxkxzdjz" in tags:
            label = (label + " rotation").strip()
        if label:
            write(
                f"  [{step:02d}] {action} -> {pos} "
                f"s={shape} c={model.color_order[color]} r={model.rotations[rot]} "
                f"energy={energy} goals={len(completed_goals)}/{len(model.goals)} {label}"
            )

    try:
        ok, solved_step = execute_plan(plan, write)
        result = ExecutionResult(executed=True, success=ok, solved_step=solved_step)
    except ModuleNotFoundError as exc:
        result = ExecutionResult(executed=False, success=None, reason=str(exc))
        write(f"\nARC runtime unavailable, skipped execution: {exc}")
    if result.executed:
        if result.solved_step is not None and result.solved_step != len(plan):
            write(
                f"Observed runtime solve-step {result.solved_step} differs from "
                f"static plan length {len(plan)}; pusher timing is more favorable than the model."
            )
        write("\nFINAL: " + ("SUCCESS" if result.success else "FAILED"))
    else:
        write("\nFINAL: STATIC_PLAN_ONLY")
    try:
        summary = {
            "plan": "".join(plan),
            "length": len(plan),
            "executed": result.executed,
            "success": result.success,
            "observed_solved_step": result.solved_step,
            "reason": result.reason,
            "start": model.start_cell,
            "exit": model.exit_cell,
        }
        (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    finally:
        flush()


if __name__ == "__main__":
    main()
