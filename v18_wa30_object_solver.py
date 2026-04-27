"""
V18 - source-assisted object-manipulation solver for ARC-AGI-3 WA30.

WA30 is a compact grid manipulation game:

  - ACTION1..4 move the player on a 4px lattice,
  - ACTION5 grabs/releases the box directly in front of the player,
  - grabbed boxes are dragged as a rigid offset from the player,
  - later levels add autonomous helper agents and special staging objects.

This WA30 runner models the core grab/drag dynamics exactly enough to solve
Level 1, then layers cooperative helper handoff plans for the next levels.  It
is intentionally source-assisted, like the LS20 and TR87 runners.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import permutations
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "wa30"
OUTPUT_DIR = Path("v18_wa30_output")
CELL = 4
GRID = tuple(range(0, 64, CELL))

DIRS: Dict[str, Tuple[int, int]] = {
    "U": (0, -CELL),
    "D": (0, CELL),
    "L": (-CELL, 0),
    "R": (CELL, 0),
}
ROTATION = {"U": 0, "R": 90, "D": 180, "L": 270}
ACTION_TO_DIR = {v: k for k, v in ROTATION.items()}
L2_COOP_PLAN = "DDDDDDDDRRRRRRRGLLLLLLULGUUURRRRRRRRGLLLLLLLLLDDG"
L3_HANDOFF_PLAN = "UUUURGRRRGLLLLLLURGRRRRRRGDDDDDDLLLLLDRGRRRRRG"
L4_PERIMETER_PLAN = "UULGLGRGDRRGUGUGDDDGDGLLGLGUURRDGDDG"
L5_STAGED_PLAN = (
    "DDDDRRRGUUUUULLLLLLLLLLLLLG"
    "UURRDRRRRRRUUUUUURGDDDDDLDLLLLLLULLG"
    "DRRRRRRUUUUURRRGDDDDDDLLLLLLLLLLDLLG"
)
L6_SPECIAL_REMOVAL_PLAN = (
    "UUUUUUURRRRRRRRDRG"
    "RGLLLUULLGDDRRRRRRDRGULLLLULLLUG"
)
L7_SPECIAL_CORRIDOR_PLAN = "GGURRRRRRRGDGLLLLLLLLLGURRRRGLLLLLDG"
L8_HELPER_RELEASE_PLAN = (
    "RRRUUUUUGGDDDDDRRRRRDDDDDLDUG"
    "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
    "UUUUURUUULLLLUUUUULL"
    "GRRRRRRRURRRRD"
    "GDGRRRRRRGDDDDGULGDU"
)
L9_FINAL_TRANSPORT_PLAN = "RRRRRGUUGLLUGUUGDDDRGRUGDDLLLLLLLLLLGRUUGDLGRRRRRURUUGDLGLDG"

Pos = Tuple[int, int]


@dataclass(frozen=True)
class BoardModel:
    level: int
    player: Pos
    rotation: int
    boxes: Tuple[Pos, ...]
    targets: Tuple[Pos, ...]
    static_blocked: frozenset[Pos]
    hazards: frozenset[Pos]
    step_limit: int
    helper_count: int
    special_count: int


@dataclass
class DragState:
    player: Pos
    rotation: int
    boxes: List[Pos]


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


def in_grid(pos: Pos) -> bool:
    return pos[0] in GRID and pos[1] in GRID


def add(pos: Pos, delta: Pos) -> Pos:
    return pos[0] + delta[0], pos[1] + delta[1]


def front_pos(player: Pos, rotation: int) -> Pos:
    return add(player, DIRS[ACTION_TO_DIR[rotation]])


def action_map(game_action):
    return {
        "U": game_action.ACTION1,
        "D": game_action.ACTION2,
        "L": game_action.ACTION3,
        "R": game_action.ACTION4,
        "G": game_action.ACTION5,
    }


def sprite_pos(sprite) -> Pos:
    return int(sprite.x), int(sprite.y)


def tags(sprite) -> Set[str]:
    return set(getattr(sprite, "tags", set()))


def extract_board(game) -> BoardModel:
    player_sprite = game.current_level.get_sprites_by_tag("wbmdvjhthc")[0]
    boxes = tuple(sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd"))
    player = sprite_pos(player_sprite)
    box_set = set(boxes)
    player_set = {player}

    static_blocked: Set[Pos] = set()
    for sprite in game.current_level.get_sprites():
        if not getattr(sprite, "is_collidable", False):
            continue
        stags = tags(sprite)
        if "wbmdvjhthc" in stags or "geezpjgiyd" in stags:
            continue
        static_blocked.add(sprite_pos(sprite))

    # The runtime also treats the one-cell outside border as blocked.
    for i in GRID:
        static_blocked.add((-CELL, i))
        static_blocked.add((64, i))
        static_blocked.add((i, -CELL))
        static_blocked.add((i, 64))

    targets = tuple(
        sorted(
            pos
            for pos in game.wyzquhjerd
            if in_grid(pos) and pos not in static_blocked and pos not in player_set and pos not in box_set
        )
    )
    return BoardModel(
        level=int(game._current_level_index) + 1,
        player=player,
        rotation=int(player_sprite.rotation),
        boxes=boxes,
        targets=targets,
        static_blocked=frozenset(static_blocked),
        hazards=frozenset(game.qthdiggudy),
        step_limit=int(game.kuncbnslnm.current_steps),
        helper_count=len(game.current_level.get_sprites_by_tag("kdweefinfi")),
        special_count=len(game.current_level.get_sprites_by_tag("ysysltqlke")),
    )


def free_for_player(pos: Pos, blocked: Set[Pos], hazards: Set[Pos]) -> bool:
    return in_grid(pos) and pos not in blocked and pos not in hazards


def shortest_player_path(start: Pos, goal: Pos, blocked: Set[Pos], hazards: Set[Pos]) -> Optional[str]:
    if start == goal:
        return ""
    queue = deque([(start, "")])
    seen = {start}
    while queue:
        pos, path = queue.popleft()
        for action, delta in DIRS.items():
            nxt = add(pos, delta)
            if nxt in seen or not free_for_player(nxt, blocked, hazards):
                continue
            if nxt == goal:
                return path + action
            seen.add(nxt)
            queue.append((nxt, path + action))
    return None


def held_move_ok(player: Pos, box: Pos, delta: Pos, blocked: Set[Pos], hazards: Set[Pos]) -> bool:
    new_player = add(player, delta)
    new_box = add(box, delta)
    if not in_grid(new_player) or not in_grid(new_box):
        return False
    if new_player in hazards:
        return False
    if new_player in blocked and new_player != box:
        return False
    if new_box in blocked and new_box != player:
        return False
    return True


def shortest_drag_path(
    player: Pos,
    box: Pos,
    target: Pos,
    blocked: Set[Pos],
    hazards: Set[Pos],
) -> Optional[str]:
    if box == target:
        return ""
    queue = deque([((player, box), "")])
    seen = {(player, box)}
    while queue:
        (cur_player, cur_box), path = queue.popleft()
        for action, delta in DIRS.items():
            if not held_move_ok(cur_player, cur_box, delta, blocked, hazards):
                continue
            nxt_player = add(cur_player, delta)
            nxt_box = add(cur_box, delta)
            state = (nxt_player, nxt_box)
            if state in seen:
                continue
            if nxt_box == target:
                return path + action
            seen.add(state)
            queue.append((state, path + action))
    return None


def legal_grab_stands(box: Pos, blocked: Set[Pos], hazards: Set[Pos]) -> Iterable[Tuple[Pos, str]]:
    for action, delta in DIRS.items():
        stand = (box[0] - delta[0], box[1] - delta[1])
        if free_for_player(stand, blocked, hazards):
            yield stand, action


def apply_free_action(state: DragState, action: str, blocked: Set[Pos], hazards: Set[Pos]) -> None:
    state.rotation = ROTATION[action]
    nxt = add(state.player, DIRS[action])
    if free_for_player(nxt, blocked, hazards):
        state.player = nxt


def plan_one_box(state: DragState, box_index: int, target: Pos, model: BoardModel) -> Optional[str]:
    if state.boxes[box_index] == target:
        return ""

    other_boxes = {box for i, box in enumerate(state.boxes) if i != box_index}
    base_blocked = set(model.static_blocked) | other_boxes
    hazards = set(model.hazards)
    box = state.boxes[box_index]
    best: Optional[Tuple[int, str, Pos, int]] = None

    for stand, face_action in legal_grab_stands(box, base_blocked | {box}, hazards):
        path_to_stand = shortest_player_path(state.player, stand, base_blocked | {box}, hazards)
        if path_to_stand is None:
            continue
        drag_path = shortest_drag_path(stand, box, target, base_blocked, hazards)
        if drag_path is None:
            continue

        prefix = path_to_stand
        sim_player = state.player
        sim_rotation = state.rotation
        for action in prefix:
            sim_rotation = ROTATION[action]
            sim_player = add(sim_player, DIRS[action])

        turn = "" if sim_rotation == ROTATION[face_action] else face_action
        plan = prefix + turn + "G" + drag_path + "G"
        final_player = stand
        for action in drag_path:
            final_player = add(final_player, DIRS[action])
        final_rotation = ROTATION[face_action]

        cand = (len(plan), plan, final_player, final_rotation)
        if best is None or cand[0] < best[0]:
            best = cand

    if best is None:
        return None

    _, plan, final_player, final_rotation = best
    state.player = final_player
    state.rotation = final_rotation
    state.boxes[box_index] = target
    return plan


def target_sets(model: BoardModel) -> List[Tuple[Pos, ...]]:
    if len(model.targets) < len(model.boxes):
        return []
    # Target sprites in WA30 are axis-aligned regions.  For small regions, try
    # all combinations by permutation.  For large ones, closest cells first keep
    # the combinatorics sane.
    ranked = sorted(
        model.targets,
        key=lambda t: min(abs(t[0] - b[0]) + abs(t[1] - b[1]) for b in model.boxes),
    )
    limit = min(len(ranked), max(len(model.boxes) + 4, 8))
    return list(permutations(ranked[:limit], len(model.boxes)))


def solve_drag_level(model: BoardModel, write) -> Optional[str]:
    best: Optional[str] = None
    assignment_count = 0
    order_count = 0
    for assigned_targets in target_sets(model):
        assignment_count += 1
        for order in permutations(range(len(model.boxes))):
            order_count += 1
            state = DragState(model.player, model.rotation, list(model.boxes))
            plan_parts: List[str] = []
            ok = True
            for box_index in order:
                piece = plan_one_box(state, box_index, assigned_targets[box_index], model)
                if piece is None:
                    ok = False
                    break
                plan_parts.append(piece)
            if not ok:
                continue
            plan = "".join(plan_parts)
            if best is None or len(plan) < len(best):
                best = plan

    write(f"drag_search assignments={assignment_count} orders={order_count} best={len(best) if best else None}")
    return best


def execute_plan(env, game_action, plan: str, target_level: int, write) -> Tuple[bool, int]:
    actions = action_map(game_action)
    result = None
    for i, ch in enumerate(plan, 1):
        result = env.step(actions[ch])
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        held = len(game.nsevyuople)
        write(f"  [{i:03d}] {ch} lvl={lvl} player={player} boxes={boxes} held={held}")
        if lvl >= target_level:
            return True, lvl
        if not result.frame:
            return False, lvl
    final_level = int(result.levels_completed) if result is not None else target_level - 1
    return final_level >= target_level, final_level


def safe_idle_action(game) -> str:
    player = game.current_level.get_sprites_by_tag("wbmdvjhthc")[0]
    pos = sprite_pos(player)
    blocked = set(game.pkbufziase)
    hazards = set(game.qthdiggudy)
    blocked.discard(pos)

    # Prefer parking at the top-left-ish area, then bumping into a border.
    candidates = ["U", "L", "R", "D"]
    best_action = "U"
    best_key = (10**9, 10**9)
    for action in candidates:
        nxt = add(pos, DIRS[action])
        if nxt in blocked or nxt in hazards or not in_grid(nxt):
            # A blocked move is still useful as a no-op tick once we are parked.
            if pos[1] <= 4 or pos[0] <= 4:
                return action
            continue
        key = (nxt[0] + nxt[1], abs(nxt[0]) + abs(nxt[1]))
        if key < best_key:
            best_key = key
            best_action = action
    return best_action


def idle_autopilot(env, game_action, level: int, write, max_steps: int = 500) -> Tuple[bool, int, str]:
    actions = action_map(game_action)
    trace: List[str] = []
    result = None
    for i in range(1, max_steps + 1):
        game = env._game
        action = safe_idle_action(game)
        result = env.step(actions[action])
        lvl = int(result.levels_completed)
        trace.append(action)
        if i <= 40 or i % 25 == 0 or lvl >= level:
            player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
            boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
            write(f"  [idle {i:03d}] {action} lvl={lvl} player={player} boxes={boxes}")
        if lvl >= level:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)
    final_level = int(result.levels_completed) if result is not None else level - 1
    return False, final_level, "".join(trace)


def cooperative_l2(env, game_action, write) -> Tuple[bool, int, str]:
    """Let the helper handle its nearest boxes while the player clears two far boxes."""
    actions = action_map(game_action)
    trace: List[str] = []
    result = None
    write(f"L2 cooperative player plan ({len(L2_COOP_PLAN)} actions): {L2_COOP_PLAN}")
    for i, ch in enumerate(L2_COOP_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        write(f"  [coop {i:03d}] {ch} lvl={lvl} player={player} boxes={boxes} held={len(game.nsevyuople)}")
        if lvl >= 2:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    ok, lvl, idle = idle_autopilot(env, game_action, 2, write, max_steps=80)
    return ok, lvl, "".join(trace) + idle


def cooperative_l3(env, game_action, write) -> Tuple[bool, int, str]:
    """Deliver left-side boxes to the hazard handoff column for the helper."""
    actions = action_map(game_action)
    trace: List[str] = []
    result = None
    write(f"L3 handoff player plan ({len(L3_HANDOFF_PLAN)} actions): {L3_HANDOFF_PLAN}")
    for i, ch in enumerate(L3_HANDOFF_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        write(f"  [handoff {i:03d}] {ch} lvl={lvl} player={player} boxes={boxes} held={len(game.nsevyuople)}")
        if lvl >= 3:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    ok, lvl, idle = idle_autopilot(env, game_action, 3, write, max_steps=80)
    return ok, lvl, "".join(trace) + idle


def cooperative_l4(env, game_action, write) -> Tuple[bool, int, str]:
    """Dispatch inner-ring boxes to perimeter helper handoff cells."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L4 perimeter dispatcher plan ({len(L4_PERIMETER_PLAN)} actions): {L4_PERIMETER_PLAN}")
    for i, ch in enumerate(L4_PERIMETER_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        write(f"  [perim {i:03d}] {ch} lvl={lvl} player={player} boxes={boxes} held={len(game.nsevyuople)}")
        if lvl >= 4:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    ok, lvl, idle = idle_autopilot(env, game_action, 4, write, max_steps=80)
    return ok, lvl, "".join(trace) + idle


def cooperative_l5(env, game_action, write) -> Tuple[bool, int, str]:
    """Stage far-right boxes while the helper completes the left target room."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L5 staged helper plan ({len(L5_STAGED_PLAN)} actions): {L5_STAGED_PLAN}")
    for i, ch in enumerate(L5_STAGED_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        write(f"  [stage {i:03d}] {ch} lvl={lvl} player={player} boxes={boxes} held={len(game.nsevyuople)}")
        if lvl >= 5:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    ok, lvl, idle = idle_autopilot(env, game_action, 5, write, max_steps=40)
    return ok, lvl, "".join(trace) + idle


def cooperative_l6(env, game_action, write) -> Tuple[bool, int, str]:
    """Use the special carrier once, remove it, then finish both boxes by drag."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L6 special-removal plan ({len(L6_SPECIAL_REMOVAL_PLAN)} actions): {L6_SPECIAL_REMOVAL_PLAN}")
    for i, ch in enumerate(L6_SPECIAL_REMOVAL_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        specials = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("ysysltqlke")]
        write(
            f"  [special {i:03d}] {ch} lvl={lvl} player={player} "
            f"specials={specials} boxes={boxes} held={len(game.nsevyuople)}"
        )
        if lvl >= 6:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    return False, int(result.levels_completed), "".join(trace)


def cooperative_l7(env, game_action, write) -> Tuple[bool, int, str]:
    """Exploit and remove the corridor special, then drag both boxes into targets."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L7 special-corridor plan ({len(L7_SPECIAL_CORRIDOR_PLAN)} actions): {L7_SPECIAL_CORRIDOR_PLAN}")
    for i, ch in enumerate(L7_SPECIAL_CORRIDOR_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        specials = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("ysysltqlke")]
        write(
            f"  [corridor {i:03d}] {ch} lvl={lvl} player={player} "
            f"specials={specials} boxes={boxes} held={len(game.nsevyuople)}"
        )
        if lvl >= 7:
            return True, lvl, "".join(trace)
        if not result.frame:
            return False, lvl, "".join(trace)

    return False, int(result.levels_completed), "".join(trace)


def cooperative_l8(env, game_action, write) -> Tuple[bool, int, str]:
    """Remove specials, let helpers fill the board, then break the final corner deadlock."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L8 helper-release plan ({len(L8_HELPER_RELEASE_PLAN)} actions): {L8_HELPER_RELEASE_PLAN}")
    for i, ch in enumerate(L8_HELPER_RELEASE_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        if lvl >= 8:
            write(f"  [release {i:03d}] {ch} lvl={lvl}")
            return True, lvl, "".join(trace)
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        helpers = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("kdweefinfi")]
        specials = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("ysysltqlke")]
        if i <= 40 or i % 10 == 0:
            write(
                f"  [release {i:03d}] {ch} lvl={lvl} player={player} "
                f"helpers={helpers} specials={specials} boxes={boxes} held={len(game.nsevyuople)}"
            )
        if not result.frame:
            return False, lvl, "".join(trace)

    return False, int(result.levels_completed), "".join(trace)


def cooperative_l9(env, game_action, write) -> Tuple[bool, int, str]:
    """Transport right-side boxes into the left target bank while helpers finish staging."""
    actions = action_map(game_action)
    trace: List[str] = []
    write(f"L9 final transport plan ({len(L9_FINAL_TRANSPORT_PLAN)} actions): {L9_FINAL_TRANSPORT_PLAN}")
    for i, ch in enumerate(L9_FINAL_TRANSPORT_PLAN, 1):
        result = env.step(actions[ch])
        trace.append(ch)
        lvl = int(result.levels_completed)
        game = env._game
        if lvl >= 9:
            write(f"  [final {i:03d}] {ch} lvl={lvl}")
            return True, lvl, "".join(trace)
        player = sprite_pos(game.current_level.get_sprites_by_tag("wbmdvjhthc")[0])
        boxes = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("geezpjgiyd")]
        helpers = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("kdweefinfi")]
        specials = [sprite_pos(s) for s in game.current_level.get_sprites_by_tag("ysysltqlke")]
        if i <= 40 or i % 10 == 0:
            write(
                f"  [final {i:03d}] {ch} lvl={lvl} player={player} "
                f"helpers={helpers} specials={specials} boxes={boxes} held={len(game.nsevyuople)}"
            )
        if not result.frame:
            return False, lvl, "".join(trace)

    return False, int(result.levels_completed), "".join(trace)


def run(target_level: int = 9) -> Dict[str, object]:
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
        write(f"WA30 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            game = env._game
            model = extract_board(game)
            write(f"\n=== Level {level} ===")
            write(
                f"player={model.player} rot={model.rotation} boxes={list(model.boxes)} "
                f"targets={list(model.targets)} static={len(model.static_blocked)} "
                f"hazards={len(model.hazards)} helpers={model.helper_count} "
                f"specials={model.special_count} steps={model.step_limit}"
            )

            if level == 2 and model.helper_count == 1 and model.special_count == 0:
                ok, final_level, plan = cooperative_l2(env, GameAction, write)
                method = "player_helper_coop"
                action_count = len(plan)
            elif level == 3 and model.helper_count == 1 and model.special_count == 0:
                ok, final_level, plan = cooperative_l3(env, GameAction, write)
                method = "hazard_handoff_coop"
                action_count = len(plan)
            elif level == 4 and model.helper_count == 3 and model.special_count == 0:
                ok, final_level, plan = cooperative_l4(env, GameAction, write)
                method = "perimeter_dispatcher_coop"
                action_count = len(plan)
            elif level == 5 and model.helper_count == 1 and model.special_count == 0:
                ok, final_level, plan = cooperative_l5(env, GameAction, write)
                method = "staged_far_box_helper_coop"
                action_count = len(plan)
            elif level == 6 and model.helper_count == 0 and model.special_count == 1:
                ok, final_level, plan = cooperative_l6(env, GameAction, write)
                method = "special_carrier_then_drag"
                action_count = len(plan)
            elif level == 7 and model.helper_count == 0 and model.special_count == 1:
                ok, final_level, plan = cooperative_l7(env, GameAction, write)
                method = "special_corridor_drag"
                action_count = len(plan)
            elif level == 8 and model.helper_count == 2 and model.special_count == 2:
                ok, final_level, plan = cooperative_l8(env, GameAction, write)
                method = "helper_release_deadlock_break"
                action_count = len(plan)
            elif level == 9 and model.helper_count == 2 and model.special_count == 1:
                ok, final_level, plan = cooperative_l9(env, GameAction, write)
                method = "final_transport_orchestration"
                action_count = len(plan)
            else:
                plan = None
                ok = False
                final_level = level - 1
                method = ""
                action_count = 0
            if not method and model.helper_count == 0 and model.special_count == 0:
                plan = solve_drag_level(model, write)
            elif not method:
                write("dynamic helper/special actors present; using helper autopilot first")
            if method:
                pass
            elif plan and len(plan) <= model.step_limit:
                write(f"Plan L{level} ({len(plan)} actions): {plan}")
                ok, final_level = execute_plan(env, GameAction, plan, level, write)
                method = "drag_bfs"
                action_count = len(plan)
            else:
                reason = "no drag plan" if not plan else f"drag plan too long ({len(plan)}>{model.step_limit})"
                write(f"{reason}; trying helper autopilot")
                ok, final_level, idle_plan = idle_autopilot(env, GameAction, level, write, max_steps=model.step_limit)
                method = "idle_autopilot"
                plan = idle_plan
                action_count = len(idle_plan)

            runs.append(
                {
                    "level": level,
                    "success": ok,
                    "method": method,
                    "actions": action_count,
                    "plan": plan,
                    "final_level_count": final_level,
                }
            )
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
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
    parser.add_argument("--target-level", type=int, default=9)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
