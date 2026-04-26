"""
Potential Field Layer — Laplace BVP navigation.

We solve ∇²φ = 0 on walkable cells with:
  - Dirichlet φ = 0 at the EXIT (sink).
  - Dirichlet φ = +large at walls / unreachable (source, repulsive).
  - Point sources at UN-FIRED triggers (weighted by how many crossings
    still needed) — so the gradient pulls us through triggers before exit.
  - Point sinks at collectibles we still need (refill stations).

Result: φ(cell) is a harmonic potential. Action selection = steepest descent
on φ. Unlike A*, this is smooth, handles multiple soft objectives, and
naturally balances "go to exit" vs "detour through a trigger" via source
weights.

Why this is unusual for ARC: standard solvers use discrete graph search
(BFS/A*). We use continuous PDE intuition on a discrete grid. The math
behind it (harmonic functions, mean-value property, maximum principle)
gives guarantees — no local minima inside the walkable region except at
the designated sinks.

Implementation: Gauss-Seidel relaxation on the cell lattice. Fast enough
(<100 iters) for 64x64 grids.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
import numpy as np
import networkx as nx


DELTA4 = [('U', -5, 0), ('D', 5, 0), ('L', 0, -5), ('R', 0, 5)]


@dataclass
class FieldSpec:
    """Boundary conditions / sources for the BVP."""
    walkable: Set[Tuple[int, int]]
    exit_cell: Optional[Tuple[int, int]] = None
    # Triggers with remaining required crossings: cell -> count (>=1 means
    # must still be hit). Modeled as positive point sources (attractors
    # stronger than exit sink until count hits 0).
    triggers_remaining: Dict[Tuple[int, int], int] = field(default_factory=dict)
    # Collectibles still needed: cell -> priority weight (1.0 = normal).
    collectibles_remaining: Dict[Tuple[int, int], float] = field(default_factory=dict)
    # Extra no-go cells (dynamic hazards).
    hazards: Set[Tuple[int, int]] = field(default_factory=set)


@dataclass
class PotentialField:
    phi: Dict[Tuple[int, int], float]
    spec: FieldSpec

    def action_at(self, cell: Tuple[int, int]) -> Optional[str]:
        """Steepest-descent action. Returns 'U'/'D'/'L'/'R' or None."""
        best_a, best_v = None, self.phi.get(cell, float('inf'))
        for a, dr, dc in DELTA4:
            nb = (cell[0] + dr, cell[1] + dc)
            if nb in self.spec.walkable and nb not in self.spec.hazards:
                v = self.phi.get(nb, float('inf'))
                if v < best_v:
                    best_v = v
                    best_a = a
        return best_a

    def trajectory(self, start: Tuple[int, int], max_len: int = 200
                   ) -> List[str]:
        """Greedy rollout along −∇φ until we hit exit or a plateau."""
        out = []
        cur = start
        visited = {cur}
        for _ in range(max_len):
            if cur == self.spec.exit_cell:
                break
            a = self.action_at(cur)
            if a is None:
                break
            dr, dc = {'U': (-5, 0), 'D': (5, 0),
                      'L': (0, -5), 'R': (0, 5)}[a]
            nxt = (cur[0] + dr, cur[1] + dc)
            if nxt in visited:  # plateau — bail
                break
            visited.add(nxt)
            out.append(a)
            cur = nxt
        return out


def solve_laplace(spec: FieldSpec,
                  max_iters: int = 2000,
                  tol: float = 1e-4,
                  exit_value: float = 0.0,
                  wall_value: float = 1.0e3,
                  trigger_source: float = -50.0,
                  collectible_source: float = -20.0
                  ) -> PotentialField:
    """
    Gauss-Seidel iteration on the walkable lattice.

    Boundary & source convention (we MINIMIZE φ to go toward exit):
      - exit_cell: φ = 0 (fixed, global minimum)
      - hazards / off-grid: φ = wall_value (fixed, repulsive)
      - trigger with k crossings left: acts as a dirichlet well at
        trigger_source * k (more negative than exit so we're pulled in first)
      - collectible: dirichlet well at collectible_source * weight

    After all triggers/collectibles are consumed (count=0, weight=0), the
    field collapses to pure "go to exit", so the SAME solver handles
    every phase of play — no re-planning machinery needed.
    """
    walk = spec.walkable - spec.hazards
    phi = {c: 1.0 for c in walk}

    # Fixed-value cells (Dirichlet).
    fixed: Dict[Tuple[int, int], float] = {}
    if spec.exit_cell is not None and spec.exit_cell in walk:
        fixed[spec.exit_cell] = exit_value
    for cell, k in spec.triggers_remaining.items():
        if k > 0 and cell in walk:
            fixed[cell] = trigger_source * k
    for cell, wgt in spec.collectibles_remaining.items():
        if wgt > 0 and cell in walk:
            # collectibles are softer than triggers; don't overwrite a trigger
            fixed.setdefault(cell, collectible_source * wgt)
    for c, v in fixed.items():
        phi[c] = v

    # Relaxation.
    for it in range(max_iters):
        max_delta = 0.0
        for c in walk:
            if c in fixed:
                continue
            r, col = c
            acc = 0.0
            n = 0
            for _, dr, dc in DELTA4:
                nb = (r + dr, col + dc)
                if nb in phi:
                    acc += phi[nb]
                    n += 1
                else:
                    # Neumann-ish: wall acts as repulsive neighbor
                    acc += wall_value
                    n += 1
            new = acc / n
            d = abs(new - phi[c])
            if d > max_delta:
                max_delta = d
            phi[c] = new
        if max_delta < tol:
            break
    return PotentialField(phi=phi, spec=spec)


def update_after_step(pf: PotentialField, cell: Tuple[int, int]
                       ) -> PotentialField:
    """
    After stepping into `cell`: decrement trigger count / remove collectible,
    then re-solve. Incremental solve reuses previous phi as warm start
    (not yet implemented — full resolve for now; still fast).
    """
    spec = pf.spec
    new_triggers = dict(spec.triggers_remaining)
    new_colls = dict(spec.collectibles_remaining)
    if cell in new_triggers and new_triggers[cell] > 0:
        new_triggers[cell] -= 1
    if cell in new_colls:
        del new_colls[cell]
    new_spec = FieldSpec(
        walkable=spec.walkable,
        exit_cell=spec.exit_cell,
        triggers_remaining=new_triggers,
        collectibles_remaining=new_colls,
        hazards=spec.hazards,
    )
    return solve_laplace(new_spec)


def critical_points(pf: PotentialField) -> Dict[str, List[Tuple[int, int]]]:
    """
    Morse-theoretic decomposition of φ on the cell lattice.
      - minima: local sinks (should only be fixed sinks)
      - saddles: decision points (where solver must commit one way)
      - maxima: isolated repellors (hazards / wall neighbourhoods)

    Saddles are the *interesting* cells for planning: they're where
    trajectory choice is non-trivial.
    """
    mins, saddles, maxs = [], [], []
    for c, v in pf.phi.items():
        neigh_vals = []
        for _, dr, dc in DELTA4:
            nb = (c[0] + dr, c[1] + dc)
            if nb in pf.phi:
                neigh_vals.append(pf.phi[nb])
        if not neigh_vals:
            continue
        lo = min(neigh_vals)
        hi = max(neigh_vals)
        if v <= lo:
            mins.append(c)
        elif v >= hi:
            maxs.append(c)
        else:
            # crude saddle detection: sign change count around neighbourhood
            signs = [1 if nv > v else -1 for nv in neigh_vals]
            if len(set(signs)) > 1 and signs.count(1) >= 2 and signs.count(-1) >= 2:
                saddles.append(c)
    return {'minima': mins, 'saddles': saddles, 'maxima': maxs}
