"""
TDA Layer — Persistent Homology on the walkable space.

We treat the 64x64 frame as a point cloud / cubical complex and compute:
  - H0: connected components of walkable region (detects isolated pockets
        like Level 3's start cell being cut off from the main maze).
  - H1: 1-cycles (loops) in the walkable region (tells us if the maze has
        multiple routes around obstacles — critical for bounce planning).
  - Persistence values: how "stable" each feature is. Short-lived H0
        components are noise; long-lived ones are real rooms.

Output: a TopologicalSignature used by the solver to:
  (a) classify the level (tree maze vs cyclic maze vs disconnected),
  (b) detect when we need a "teleport" (pusher) to cross components,
  (c) pick good exploration frontiers (cells that kill an H1 class
      when traversed — i.e. "shortcut" moves).

Uses ripser (sparse) for speed; falls back to pure networkx if ripser missing.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Set, Dict, Optional
import numpy as np

try:
    from ripser import ripser
    HAS_RIPSER = True
except ImportError:
    HAS_RIPSER = False

import networkx as nx
from scipy import ndimage


@dataclass
class TopologicalSignature:
    # H0: connected components. Each entry is (birth, death) — for H0 birth=0.
    h0: List[Tuple[float, float]] = field(default_factory=list)
    # H1: loops.
    h1: List[Tuple[float, float]] = field(default_factory=list)
    # Number of "real" (long-lived) components — cutoff persistence > threshold.
    n_components: int = 0
    # Number of independent loops (cycle rank of walkable graph).
    n_loops: int = 0
    # Per-component cell sets (grid-level, sorted by size desc).
    components: List[Set[Tuple[int, int]]] = field(default_factory=list)
    # "Skeleton graph": nodes are grid cells, edges are 4-adjacency within walkable.
    graph: Optional[nx.Graph] = None
    # Articulation points — cells whose removal disconnects a component.
    # These are bottlenecks: killing one breaks the maze into pieces.
    articulation_cells: Set[Tuple[int, int]] = field(default_factory=set)
    # Cycle basis (list of cycles, each a list of cells). Forms H1 generators.
    cycle_basis: List[List[Tuple[int, int]]] = field(default_factory=list)

    def summary(self) -> str:
        return (f"TDA(components={self.n_components}, loops={self.n_loops}, "
                f"articulations={len(self.articulation_cells)}, "
                f"comp_sizes={[len(c) for c in self.components[:5]]})")


DELTA4 = [(-5, 0), (5, 0), (0, -5), (0, 5)]


def build_cell_graph(grid_walkable: Set[Tuple[int, int]]) -> nx.Graph:
    """Build 4-adjacency graph over walkable grid cells (step = 5 px)."""
    g = nx.Graph()
    g.add_nodes_from(grid_walkable)
    for (r, c) in grid_walkable:
        for (dr, dc) in DELTA4:
            nb = (r + dr, c + dc)
            if nb in grid_walkable:
                g.add_edge((r, c), nb)
    return g


def components_from_graph(g: nx.Graph) -> List[Set[Tuple[int, int]]]:
    comps = [set(c) for c in nx.connected_components(g)]
    comps.sort(key=len, reverse=True)
    return comps


def cycle_basis(g: nx.Graph) -> List[List[Tuple[int, int]]]:
    """Independent loops — generators of H1."""
    try:
        return [list(c) for c in nx.cycle_basis(g)]
    except Exception:
        return []


def articulation_points(g: nx.Graph) -> Set[Tuple[int, int]]:
    """Cells whose removal disconnects their component (bottlenecks)."""
    arts = set()
    for comp_nodes in nx.connected_components(g):
        sub = g.subgraph(comp_nodes)
        arts.update(nx.articulation_points(sub))
    return arts


def persistent_homology_cubical(walkable_pixel: np.ndarray
                                 ) -> Tuple[List[Tuple[float, float]],
                                            List[Tuple[float, float]]]:
    """
    Compute H0 and H1 persistence diagrams using sublevel filtration on the
    signed distance transform of the walkable mask.

    Intuition: distance-to-wall builds a natural filtration. Big open rooms
    persist long; thin corridors die fast.
    """
    if not HAS_RIPSER:
        return [], []
    # Signed distance: positive inside walkable, negative in walls.
    dt_in = ndimage.distance_transform_edt(walkable_pixel)
    dt_out = ndimage.distance_transform_edt(~walkable_pixel)
    signed = dt_out - dt_in  # smaller = more walkable
    # Subsample walkable pixels as point cloud for ripser (cubical would be
    # better but ripser core takes distance matrices / point clouds).
    ys, xs = np.where(walkable_pixel)
    if len(ys) == 0:
        return [], []
    if len(ys) > 400:  # subsample for speed
        idx = np.random.RandomState(0).choice(len(ys), 400, replace=False)
        ys, xs = ys[idx], xs[idx]
    pts = np.column_stack([ys, xs]).astype(float)
    try:
        res = ripser(pts, maxdim=1)
        dgms = res['dgms']
        h0 = [(float(b), float(d)) for b, d in dgms[0]]
        h1 = [(float(b), float(d)) for b, d in dgms[1]] if len(dgms) > 1 else []
        return h0, h1
    except Exception:
        return [], []


def compute_tda(grid_walkable: Set[Tuple[int, int]],
                walkable_pixel: Optional[np.ndarray] = None,
                persistence_threshold: float = 2.0
                ) -> TopologicalSignature:
    """Full TDA pipeline. grid_walkable is the essential input."""
    g = build_cell_graph(grid_walkable)
    comps = components_from_graph(g)
    cycles = cycle_basis(g)
    arts = articulation_points(g)

    h0, h1 = [], []
    if walkable_pixel is not None and HAS_RIPSER:
        h0, h1 = persistent_homology_cubical(walkable_pixel)

    # Filter H0/H1 by persistence. For H0, death - birth; inf deaths survive.
    def persistent(pairs):
        out = []
        for b, d in pairs:
            life = (d - b) if np.isfinite(d) else float('inf')
            if life >= persistence_threshold:
                out.append((b, d))
        return out

    sig = TopologicalSignature(
        h0=h0,
        h1=h1,
        n_components=len(comps),
        n_loops=sum(max(0, sub.number_of_edges() - sub.number_of_nodes() + 1)
                    for sub in (g.subgraph(c) for c in comps)),
        components=comps,
        graph=g,
        articulation_cells=arts,
        cycle_basis=cycles,
    )
    return sig


def classify_level(sig: TopologicalSignature) -> str:
    """
    Rough level archetype classification from topology alone.
      - 'disconnected' : >1 component → needs teleport / pusher
      - 'cyclic'       : loops present → multi-path maze (bouncing viable)
      - 'tree'         : 1 component, no loops → unique path to exit
      - 'trivial'      : 1 component, 0 cycles, few articulations → open room
    """
    if sig.n_components > 1:
        return 'disconnected'
    if sig.n_loops >= 1:
        return 'cyclic'
    if len(sig.articulation_cells) <= 1:
        return 'trivial'
    return 'tree'


def bridge_candidates(sig: TopologicalSignature
                      ) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """
    For disconnected levels: pairs of (cell_in_A, cell_in_B) that are
    closest in L1 distance across components. These are where a pusher
    teleport or boundary-breaking action is most likely to bridge.
    """
    if sig.n_components < 2:
        return []
    out = []
    A = sig.components[0]
    for B in sig.components[1:]:
        best = None
        for a in A:
            for b in B:
                d = abs(a[0] - b[0]) + abs(a[1] - b[1])
                if best is None or d < best[0]:
                    best = (d, a, b)
        if best:
            out.append((best[1], best[2]))
    return out
