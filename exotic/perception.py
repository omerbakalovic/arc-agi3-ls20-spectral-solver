"""
Perception Layer — Frame -> structured world representation.

Input: 64x64 numpy frame with discrete color values.
Output:
  - entities: list of Entity(bbox, color, pixels_mask, area, grid_aligned_cell)
  - walkable_mask: binary 64x64 — where player CAN step (inferred or known)
  - grid_cells: set of (row, col) cell coordinates (5-pixel grid) that are open
  - color_histogram: {color_value: count}
No deep learning. Just connected components + grid alignment.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
import numpy as np
from scipy import ndimage


# Grid convention for ls20-like games: cells start at col=4, row=0, step 5.
# Player occupies 5x5 cell at (row, col) => pixels [row..row+4, col..col+4].
GRID_ROW_RANGE = range(0, 61, 5)
GRID_COL_RANGE = range(4, 60, 5)
CELL_SIZE = 5


@dataclass
class Entity:
    """A single connected region of one color."""
    eid: int
    color: int                       # color value (0-15)
    bbox: Tuple[int, int, int, int]  # (rmin, cmin, rmax, cmax) inclusive
    area: int                        # num pixels
    centroid: Tuple[float, float]    # (row, col) float
    mask: np.ndarray                 # full-size bool mask
    grid_cells: Set[Tuple[int, int]] = field(default_factory=set)
    # "shape signature": compact descriptor
    shape_sig: Tuple[int, int, int] = (0, 0, 0)  # (height, width, area)
    # dynamic classification (filled later by probing)
    kind: Optional[str] = None

    @property
    def height(self) -> int: return self.bbox[2] - self.bbox[0] + 1
    @property
    def width(self) -> int: return self.bbox[3] - self.bbox[1] + 1


@dataclass
class PerceptionResult:
    frame: np.ndarray
    entities: List[Entity]
    walkable_mask: np.ndarray        # 64x64 bool: pixel-level walkability
    grid_walkable: Set[Tuple[int, int]]  # cell-level walkability
    color_hist: Dict[int, int]
    hud_rows: Tuple[int, int] = (55, 64)  # rows used by HUD, ignored for gameplay
    # entity lookup by color for quick access
    entities_by_color: Dict[int, List[Entity]] = field(default_factory=dict)


def extract_connected_components(frame: np.ndarray, hud_cutoff: int = 55
                                  ) -> List[Entity]:
    """Find all connected regions of single color in play area (rows < hud_cutoff)."""
    entities: List[Entity] = []
    eid = 0
    play = frame[:hud_cutoff, :]
    unique_colors = np.unique(play)
    for color in unique_colors:
        color_mask = (play == color)
        if not color_mask.any():
            continue
        # Label connected components (4-connectivity)
        labeled, n = ndimage.label(color_mask)
        for comp_id in range(1, n + 1):
            comp_mask = (labeled == comp_id)
            if not comp_mask.any():
                continue
            rs, cs = np.where(comp_mask)
            rmin, rmax = int(rs.min()), int(rs.max())
            cmin, cmax = int(cs.min()), int(cs.max())
            area = int(comp_mask.sum())
            centroid = (float(rs.mean()), float(cs.mean()))
            # Expand mask to full frame size
            full_mask = np.zeros_like(frame, dtype=bool)
            full_mask[:hud_cutoff, :] = comp_mask
            e = Entity(
                eid=eid,
                color=int(color),
                bbox=(rmin, cmin, rmax, cmax),
                area=area,
                centroid=centroid,
                mask=full_mask,
                shape_sig=(rmax - rmin + 1, cmax - cmin + 1, area),
            )
            # Determine which 5x5 grid cells the entity overlaps
            cells = set()
            for r in GRID_ROW_RANGE:
                for c in GRID_COL_RANGE:
                    if r + CELL_SIZE <= rmin or r > rmax:
                        continue
                    if c + CELL_SIZE <= cmin or c > cmax:
                        continue
                    # Actual pixel overlap check
                    sub = comp_mask[max(0, r):r + CELL_SIZE, max(0, c):c + CELL_SIZE]
                    if sub.any():
                        cells.add((r, c))
            e.grid_cells = cells
            entities.append(e)
            eid += 1
    return entities


def auto_floor_colors(frame: np.ndarray, player_color: int = 12,
                       hud_cutoff: int = 55) -> Set[int]:
    """
    Auto-detect walkable floor color by BFS flood-fill from the player.

    Strategy: start at the player's 5x2 footprint. For each color c that
    appears in play area, temporarily treat (play == c) as walkable and
    flood-fill 4-connected from the player's neighbours. The color whose
    flood reaches the LARGEST area is the floor — the player can traverse
    the whole floor but walls block the flood.
    """
    play = frame[:hud_cutoff, :]
    total = play.size
    counts = {int(c): int((play == c).sum()) for c in np.unique(play)
              if c != player_color}
    # Candidates: non-player colors covering >5% of play
    candidates = [c for c, n in counts.items() if n / total > 0.05]
    if not candidates:
        order = sorted(counts.items(), key=lambda x: -x[1])
        return {order[1][0]} if len(order) > 1 else {order[0][0]} if order else set()

    pmask = (play == player_color)
    if not pmask.any():
        # no player — fall back to largest single CC
        best = max(candidates, key=lambda c: int(ndimage.label(play == c)[1]))
        return {best}

    # Seeds = 4-neighbours of player mask that are NOT player
    seed_mask = np.zeros_like(pmask)
    seed_mask[1:, :]  |= pmask[:-1, :]
    seed_mask[:-1, :] |= pmask[1:, :]
    seed_mask[:, 1:]  |= pmask[:, :-1]
    seed_mask[:, :-1] |= pmask[:, 1:]
    seed_mask &= ~pmask

    best_color, best_reach = None, -1
    for c in candidates:
        fill_region = (play == c) | pmask  # allow flood through player
        labeled, _ = ndimage.label(fill_region)
        player_labels = set(np.unique(labeled[pmask]))
        player_labels.discard(0)
        if not player_labels:
            continue
        reach = sum(int((labeled == lbl).sum()) for lbl in player_labels)
        # subtract player footprint from score
        reach -= int(pmask.sum())
        if reach > best_reach:
            best_reach = reach
            best_color = c
    return {best_color} if best_color is not None else {candidates[0]}


def infer_walkability(frame: np.ndarray, entities: List[Entity],
                      background_colors: Optional[Set[int]] = None
                      ) -> Tuple[np.ndarray, Set[Tuple[int, int]]]:
    """
    Infer walkable cells by cell-level floor-color majority.
    If background_colors is None, auto-detect from the player's surroundings.

    Returns:
      pixel_mask: 64x64 bool — True where floor pixels are (conservative)
      grid_walkable: set of (row, col) cell coords with >=50% floor pixels
    """
    if background_colors is None:
        background_colors = auto_floor_colors(frame)

    walkable_pixel = np.zeros_like(frame, dtype=bool)
    for bg in background_colors:
        walkable_pixel |= (frame == bg)
    walkable_pixel[55:, :] = False  # HUD never walkable

    grid_walk = set()
    for r in GRID_ROW_RANGE:
        for c in GRID_COL_RANGE:
            region = frame[r:r+CELL_SIZE, c:c+CELL_SIZE]
            bg_pixels = sum((region == bg).sum() for bg in background_colors)
            if bg_pixels >= (CELL_SIZE * CELL_SIZE) * 0.5:
                grid_walk.add((r, c))
    return walkable_pixel, grid_walk


def perceive(frame: np.ndarray,
              floor_colors: Optional[Set[int]] = None) -> PerceptionResult:
    """Top-level: run full perception pipeline on a frame.

    If `floor_colors` is given, walkability uses that fixed set. Otherwise
    it is auto-detected from the player's surroundings (unstable across
    frames — cache the result from the first call for consistency).
    """
    entities = extract_connected_components(frame)
    walkable_mask, grid_walk = infer_walkability(frame, entities, floor_colors)
    color_hist: Dict[int, int] = {}
    for v in np.unique(frame):
        color_hist[int(v)] = int((frame == v).sum())
    by_color: Dict[int, List[Entity]] = {}
    for e in entities:
        by_color.setdefault(e.color, []).append(e)
    return PerceptionResult(
        frame=frame,
        entities=entities,
        walkable_mask=walkable_mask,
        grid_walkable=grid_walk,
        color_hist=color_hist,
        entities_by_color=by_color,
    )


def summarize(pr: PerceptionResult, top_k_per_color: int = 3) -> str:
    """Human-readable summary for debugging."""
    lines = []
    lines.append(f"Colors: {sorted(pr.color_hist.items(), key=lambda x:-x[1])[:10]}")
    lines.append(f"Entities: {len(pr.entities)} total")
    lines.append(f"Grid walkable cells: {len(pr.grid_walkable)}")
    by_color_sorted = sorted(pr.entities_by_color.items(), key=lambda x: -len(x[1]))
    for color, ents in by_color_sorted:
        lines.append(f"  color={color}: {len(ents)} entities; "
                     f"shapes={set(e.shape_sig for e in ents[:top_k_per_color])}")
        for e in ents[:top_k_per_color]:
            lines.append(f"    id={e.eid} bbox={e.bbox} area={e.area} "
                         f"cells={sorted(e.grid_cells)[:4]}")
    return "\n".join(lines)
