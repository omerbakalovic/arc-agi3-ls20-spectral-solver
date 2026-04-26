"""
Temporal-diff layer — compare two frames at the ENTITY level.

Rather than scoring walkable-set changes (which are fragile to shadow),
this module extracts discrete EVENTS between frame[t-1] and frame[t]:

  - pickup    : an entity disappeared (pixels went from non-floor to floor)
  - spawn     : a new entity appeared (floor → non-floor)
  - door_open : a wall region became floor (large, connected, adjacent to
                existing walkable)
  - motion    : an entity moved (same shape, shifted centroid)
  - noise     : tiny changes near the player (shadow)

Each event carries location + strength so the solver can prioritise.

Why this matters: ls20-style games signal progress NOT via walkable-set
deltas but via discrete object events. "Yellow key collected" is a pickup
event of 6-9 pixels at a fixed location; it may or may not also change
walkable. The solver uses these events to classify its own actions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
import numpy as np
from scipy import ndimage


@dataclass
class DiffEvent:
    kind: str                            # 'pickup' | 'spawn' | 'door_open' | 'motion' | 'noise'
    bbox: Tuple[int, int, int, int]      # (rmin, cmin, rmax, cmax)
    centroid: Tuple[float, float]
    area: int                            # number of pixels that changed
    old_color: Optional[int] = None
    new_color: Optional[int] = None
    strength: float = 0.0                # normalized salience [0, 1]


def frame_diff_events(f_prev: np.ndarray, f_curr: np.ndarray,
                       floor_colors: Set[int],
                       player_color: int = 12,
                       hud_cutoff: int = 55,
                       player_pos: Optional[Tuple[int, int]] = None
                       ) -> List[DiffEvent]:
    """Detect discrete events between two frames."""
    assert f_prev.shape == f_curr.shape
    play_prev = f_prev[:hud_cutoff, :]
    play_curr = f_curr[:hud_cutoff, :]

    changed = (play_prev != play_curr)
    # Kill player-sprite shadow: mask a 7x7 zone around known player position
    # in either frame so motion of the player isn't classified as an event.
    if player_pos is not None:
        pr, pc = player_pos
        r0, r1 = max(0, pr-3), min(hud_cutoff, pr+8)
        c0, c1 = max(0, pc-3), min(f_prev.shape[1], pc+8)
        changed[r0:r1, c0:c1] = False
    # Also mask actual player pixels in both frames (safety)
    changed &= ~((play_prev == player_color) | (play_curr == player_color))

    if not changed.any():
        return []

    # Connected components of the changed mask
    labeled, n = ndimage.label(changed)
    events: List[DiffEvent] = []
    for comp_id in range(1, n + 1):
        comp = (labeled == comp_id)
        area = int(comp.sum())
        if area < 2:
            continue                          # too small — likely noise
        rs, cs = np.where(comp)
        rmin, rmax = int(rs.min()), int(rs.max())
        cmin, cmax = int(cs.min()), int(cs.max())
        centroid = (float(rs.mean()), float(cs.mean()))

        # What did this region BECOME and what was it BEFORE?
        old_vals = play_prev[comp]
        new_vals = play_curr[comp]
        old_mode = int(np.bincount(old_vals, minlength=16).argmax())
        new_mode = int(np.bincount(new_vals, minlength=16).argmax())

        # Classification heuristic
        old_was_floor = old_mode in floor_colors
        new_is_floor = new_mode in floor_colors

        if old_was_floor and not new_is_floor:
            kind = 'spawn'
        elif not old_was_floor and new_is_floor:
            # pickup (small) vs door_open (big, connected to floor)
            kind = 'pickup' if area <= 12 else 'door_open'
        elif old_mode != new_mode:
            kind = 'motion'                  # color-swap suggesting movement
        else:
            kind = 'noise'

        strength = min(1.0, area / 25.0)     # 25 px = one full cell
        events.append(DiffEvent(kind=kind,
                                 bbox=(rmin, cmin, rmax, cmax),
                                 centroid=centroid,
                                 area=area,
                                 old_color=old_mode,
                                 new_color=new_mode,
                                 strength=strength))
    events.sort(key=lambda e: -e.strength)
    return events


def summarize_events(events: List[DiffEvent]) -> str:
    if not events:
        return "no events"
    parts = []
    for e in events:
        parts.append(f"{e.kind}@({int(e.centroid[0])},{int(e.centroid[1])})"
                     f" a={e.area} {e.old_color}->{e.new_color}")
    return " | ".join(parts)


def is_progress(events: List[DiffEvent],
                 player_pos_before: Optional[Tuple[int, int]] = None,
                 player_pos_after: Optional[Tuple[int, int]] = None) -> bool:
    """Did an action cause MEANINGFUL change? (not just shadow/noise)

    A `motion` event whose centroid lies near either player position is
    almost certainly the player sprite shifting; we discard such events.
    Genuine world changes are pickup/door_open/spawn events, OR motion
    events that are FAR from where the player was/is.
    """
    def _near_player(centroid):
        if player_pos_before is None and player_pos_after is None:
            return False
        for p in (player_pos_before, player_pos_after):
            if p is None: continue
            if abs(centroid[0] - p[0]) <= 6 and abs(centroid[1] - p[1]) <= 6:
                return True
        return False

    for e in events:
        if e.kind in ('pickup', 'door_open'):
            return True
        if e.kind == 'spawn' and not _near_player(e.centroid):
            return True
        if e.kind == 'motion' and e.area >= 6 and not _near_player(e.centroid):
            return True
    return False
