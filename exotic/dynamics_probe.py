"""
Dynamics Probing Layer — learn what unknown entities DO.

Perception tells us "there's a red 5x5 block at (10, 49)". It does NOT
tell us if that block is:
  - a wall (blocks movement, no effect)
  - a collectible (disappears when touched, refills counter)
  - a trigger (survives contact, mutates global state)
  - a pusher (teleports player to another location)
  - the exit (ends level)

We find out by POKING. For each mystery entity, we try to walk into it
from every reachable neighbouring cell and observe the frame delta:

    frame_before vs frame_after(action)

Classification rules derived from observation:

    Δplayer_pos = 0, entity unchanged, no global change
        → WALL
    Δplayer_pos = 0, entity DISAPPEARS, counter_color pixel count ↑
        → COLLECTIBLE
    Δplayer_pos = 0, entity unchanged, OTHER entity transformed
        → TRIGGER (record which other entity changed: rotation/color/shape)
    Δplayer_pos = LARGE (>5 px jump), entity unchanged
        → PUSHER (record source->dest delta, direction)
    frame = None (death) OR level_completed ↑
        → EXIT (or hazard if no level progression)

This is *active inference* in the cheap sense: we literally run experiments
to reduce uncertainty. One probe per entity × direction = O(4|entities|)
steps of "wasted" play, but it's a one-time cost per level and makes the
solver fully general — no hardcoded sprite names.

Caveat: triggers have CUMULATIVE effects (rotation +90° each crossing).
We infer the group order by probing until we see the state cycle back
to original. For ls20, typically C_4 (four crossings = identity).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable
import numpy as np


# Kind codes.
KIND_WALL = 'wall'
KIND_COLLECTIBLE = 'collectible'
KIND_TRIGGER = 'trigger'
KIND_PUSHER = 'pusher'
KIND_EXIT = 'exit'
KIND_HAZARD = 'hazard'
KIND_UNKNOWN = 'unknown'


@dataclass
class ProbeResult:
    entity_id: int
    kind: str
    # For trigger: which OTHER entity changed and how (delta tuple or string).
    trigger_effect: Optional[str] = None
    # For pusher: (src_cell, dst_cell, direction).
    pusher_src: Optional[Tuple[int, int]] = None
    pusher_dst: Optional[Tuple[int, int]] = None
    pusher_dir: Optional[str] = None
    # For trigger with cyclic modifier: inferred group order (e.g. 4).
    cycle_order: Optional[int] = None
    # Raw evidence (probe action, before/after summary) for debugging.
    evidence: List[str] = field(default_factory=list)


@dataclass
class ProbeReport:
    results: Dict[int, ProbeResult]     # entity_id -> result
    trigger_cells: Dict[Tuple[int, int], Tuple[int, int, int]]  # cell -> (dr, dc, ds)
    pusher_map: Dict[Tuple[int, int], Tuple[int, int]]          # src -> dst
    walls: List[int]
    collectibles: List[int]
    exit_cell: Optional[Tuple[int, int]] = None


def frame_diff(a: np.ndarray, b: np.ndarray) -> float:
    """L1 pixel difference."""
    if a is None or b is None:
        return float('inf')
    return float(np.abs(a.astype(int) - b.astype(int)).sum())


def detect_player_pos(frame: np.ndarray, player_color: int = 12
                       ) -> Optional[Tuple[int, int]]:
    """5x2 block of player_color in play area."""
    if frame is None:
        return None
    mask = (frame[:55, :] == player_color)
    if not mask.any():
        return None
    h, w = mask.shape
    for y in range(h - 1):
        for x in range(w - 4):
            if mask[y:y+2, x:x+5].all():
                return (y, x)
    return None


def _neighbour_approach_dirs(entity_bbox, walkable_cells):
    """Yield (approach_cell, action) pairs to walk into the entity."""
    rmin, cmin, rmax, cmax = entity_bbox
    # Try 4 cardinal approaches
    cands = [
        ((rmax + 1 + 0, cmin), 'U'),  # approach from below, move up
        ((rmin - 5, cmin), 'D'),      # approach from above, move down
        ((rmin, cmax + 1), 'L'),      # approach from right, move left
        ((rmin, cmin - 5), 'R'),      # approach from left, move right
    ]
    # Snap to nearest walkable cell
    for (ar, ac), act in cands:
        # Find walkable cell closest to (ar, ac)
        best, bd = None, 10**9
        for (r, c) in walkable_cells:
            d = abs(r - ar) + abs(c - ac)
            if d < bd:
                bd, best = d, (r, c)
        if best is not None and bd <= 10:
            yield best, act


def probe_entity(env_step: Callable, get_frame: Callable,
                 nav_to: Callable, entity, walkable_cells,
                 player_color: int = 12) -> ProbeResult:
    """
    Probe one entity. Caller supplies:
      - env_step(action) -> result
      - get_frame() -> np.ndarray
      - nav_to(cell) -> bool (navigates safely; True on success)

    This function is deliberately environment-agnostic.
    """
    res = ProbeResult(entity_id=entity.eid, kind=KIND_UNKNOWN)

    for approach_cell, action in _neighbour_approach_dirs(entity.bbox,
                                                          walkable_cells):
        if not nav_to(approach_cell):
            continue
        before = get_frame()
        p_before = detect_player_pos(before, player_color)
        step_result = env_step(action)
        after = get_frame()
        p_after = detect_player_pos(after, player_color)

        if after is None or getattr(step_result, 'frame', True) is None:
            res.kind = KIND_HAZARD
            res.evidence.append(f"died on {action} from {approach_cell}")
            return res
        if hasattr(step_result, 'levels_completed') and \
                int(step_result.levels_completed) > 0:
            res.kind = KIND_EXIT
            return res

        dp = None if (p_before is None or p_after is None) else \
             (p_after[0] - p_before[0], p_after[1] - p_before[1])

        if dp is None or dp == (0, 0):
            # Didn't move. Either wall or trigger.
            # Check if entity disappeared → collectible.
            ent_before = before[entity.bbox[0]:entity.bbox[2]+1,
                                entity.bbox[1]:entity.bbox[3]+1]
            ent_after = after[entity.bbox[0]:entity.bbox[2]+1,
                              entity.bbox[1]:entity.bbox[3]+1]
            if not np.array_equal(ent_before, ent_after):
                res.kind = KIND_COLLECTIBLE
                return res
            # Frame diff elsewhere?
            d = frame_diff(before, after)
            if d > 0:
                res.kind = KIND_TRIGGER
                res.evidence.append(f"trigger fire, pixel delta={d}")
                return res
            res.kind = KIND_WALL
            return res
        else:
            # Player moved. Big jump (>5px in any axis) = pusher.
            if abs(dp[0]) > 5 or abs(dp[1]) > 5:
                res.kind = KIND_PUSHER
                res.pusher_src = p_before
                res.pusher_dst = p_after
                res.pusher_dir = action
                return res
            # Normal 5-px step: we walked THROUGH it somehow — probably
            # empty space, or a harmless decoration. Mark as passable.
            res.kind = KIND_WALL  # conservative: re-classify later
            res.evidence.append(f"passed through, dp={dp}")
            return res
    return res


def cycle_order_from_probes(deltas: List[int], modulus_guesses=(2, 3, 4, 6, 8)
                             ) -> int:
    """Infer group order from cumulative color/rotation deltas."""
    if not deltas:
        return 0
    for m in modulus_guesses:
        if sum(deltas) % m == 0 and all(d % m != 0 for d in deltas if d != 0):
            return m
    return max(modulus_guesses)
