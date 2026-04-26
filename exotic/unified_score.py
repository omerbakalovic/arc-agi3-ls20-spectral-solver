"""
Unified trigger-candidate score combining all layers of the stack.

For each grid cell c, compute:

   score(c) = w_lap * z_score(c)              [geometry]
            + w_inv * (1 - invariance(c))     [statistics — rare changes]
            + w_alg * algebra_anomaly(c)      [algebra — non-commutator failures]
            + w_tmp * event_density(c)        [temporal — pickup/door events]
            + w_calib * calibration_bonus(c)  [calibration — confirmed reachable]

Each component is normalized to [0, 1] before weighting. The result is a
single ranking that integrates all available evidence.

Why this matters: each signal alone is noisy. Geometry says "high curvature"
but that may be a wall corner. Statistics says "rarely changes" but that
may be a static decoration. Algebra says "non-commutative" but that may
be perception jitter. The CONJUNCTION of signals is what identifies real
triggers — a cell that is geometrically anomalous, statistically variable,
algebraically order-dependent, and temporally event-rich is almost
certainly the interactive entity we are looking for.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
import numpy as np


@dataclass
class UnifiedScoreInputs:
    """All evidence streams the unified score consumes."""
    laplacian_z: Dict[Tuple[int, int], float] = field(default_factory=dict)
    invariance: Dict[Tuple[int, int], float] = field(default_factory=dict)
    algebra_breakage: Dict[Tuple[int, int], int] = field(default_factory=dict)
    event_count: Dict[Tuple[int, int], int] = field(default_factory=dict)
    confirmed_walkable: Set[Tuple[int, int]] = field(default_factory=set)
    pseudo_walls: Set[Tuple[int, int]] = field(default_factory=set)
    danger_cells: Set[Tuple[int, int]] = field(default_factory=set)


@dataclass
class UnifiedScoreWeights:
    """Tunable weights — defaults reflect intuition; can be re-fit."""
    w_laplacian: float = 1.0
    w_invariance: float = 0.8
    w_algebra: float = 0.6
    w_temporal: float = 1.2
    w_calibration: float = 0.3
    danger_penalty: float = 5.0


def _normalize(d: Dict, default: float = 0.0) -> Dict:
    """Min-max normalize a dict's values to [0, 1]."""
    if not d:
        return d
    vals = list(d.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return {k: default for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def compute_unified_scores(inputs: UnifiedScoreInputs,
                            weights: UnifiedScoreWeights = None,
                            cells: Optional[List[Tuple[int, int]]] = None
                            ) -> Dict[Tuple[int, int], float]:
    """Compute unified score per cell.

    `cells` restricts which cells we score; defaults to union of all
    cells appearing in any input dictionary.
    """
    w = weights or UnifiedScoreWeights()
    # determine cell set
    if cells is None:
        cell_set: Set[Tuple[int, int]] = set()
        cell_set.update(inputs.laplacian_z.keys())
        cell_set.update(inputs.invariance.keys())
        cell_set.update(inputs.algebra_breakage.keys())
        cell_set.update(inputs.event_count.keys())
        cell_set.update(inputs.confirmed_walkable)
        cells = sorted(cell_set)

    # normalize each stream
    nz   = _normalize(inputs.laplacian_z)
    nalg = _normalize({k: float(v) for k, v in inputs.algebra_breakage.items()})
    ntmp = _normalize({k: float(v) for k, v in inputs.event_count.items()})

    out: Dict[Tuple[int, int], float] = {}
    for c in cells:
        z   = nz.get(c, 0.0)
        inv = inputs.invariance.get(c, 1.0)         # invariant → boring
        alg = nalg.get(c, 0.0)
        tmp = ntmp.get(c, 0.0)
        calib_bonus = 1.0 if c in inputs.confirmed_walkable else 0.0

        score = (w.w_laplacian   * z
               + w.w_invariance  * (1 - inv)
               + w.w_algebra     * alg
               + w.w_temporal    * tmp
               + w.w_calibration * calib_bonus)
        if c in inputs.danger_cells:
            score -= w.danger_penalty
        if c in inputs.pseudo_walls:
            score -= 0.5            # pseudo-walls are less likely BUT still possible
        out[c] = score
    return out


def top_candidates(scores: Dict[Tuple[int, int], float],
                    k: int = 10) -> List[Tuple[Tuple[int, int], float]]:
    return sorted(scores.items(), key=lambda x: -x[1])[:k]


def explain_score(c: Tuple[int, int],
                   inputs: UnifiedScoreInputs,
                   weights: UnifiedScoreWeights = None) -> str:
    """Human-readable breakdown of how a cell got its score."""
    w = weights or UnifiedScoreWeights()
    z = inputs.laplacian_z.get(c, 0.0)
    inv = inputs.invariance.get(c, 1.0)
    alg = inputs.algebra_breakage.get(c, 0)
    tmp = inputs.event_count.get(c, 0)
    parts = [
        f"laplacian_z={z:+.2f}",
        f"invariance={inv:.2f}",
        f"algebra_breaks={alg}",
        f"events={tmp}",
        f"confirmed_walk={c in inputs.confirmed_walkable}",
        f"pseudo_wall={c in inputs.pseudo_walls}",
        f"danger={c in inputs.danger_cells}",
    ]
    return f"cell {c}: " + ", ".join(parts)
