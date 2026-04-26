"""
Group-Theoretic State Layer.

The insight: ls20 and similar ARC games have a small set of "modifiers"
(rotation, color, shape) each living in a cyclic group C_n. The full game
state modulo position is a product of cyclic groups:

    G = C_{rot} × C_{col} × C_{shape} × ...  × 2^{collectibles}

Planning = finding a word in generators {trigger_actions} that maps the
current group element to the goal coset. This is EXACTLY the word problem
in an abelian group — solvable in O(|G|) via BFS on the Cayley graph,
which is tiny (a few hundred nodes at most for typical puzzles).

Crucial abstraction: positional navigation (handled by potential_field)
is decoupled from modifier state (handled here). The two communicate via
"trigger crossing events". We can plan modifier transitions WITHOUT
worrying about paths — just count crossings needed per trigger — then
hand those counts to the potential field which figures out the routing.

This is unusually clean. No one at ARC uses group theory. They hammer
everything with search on the full product space (position × modifiers).
We factor it, exploiting the algebraic structure the game actually has.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, FrozenSet
from collections import deque


@dataclass(frozen=True)
class GroupState:
    """Position-independent game state. All modifiers live here."""
    rotation: int = 0     # in C_{rot_mod}
    color: int = 0        # in C_{col_mod}
    shape: int = 0        # in C_{shape_mod}
    collected: FrozenSet[Tuple[int, int]] = frozenset()

    def tup(self) -> tuple:
        return (self.rotation, self.color, self.shape, self.collected)


@dataclass
class GroupSpec:
    """Defines the finite group we're working in."""
    rot_mod: int = 4      # C_4 rotation (0°, 90°, 180°, 270°)
    col_mod: int = 4      # C_4 color cycle
    shape_mod: int = 4    # C_k shape cycle
    # Triggers: cell -> (delta_rot, delta_col, delta_shape).
    # Crossing the trigger adds these deltas modulo the group.
    triggers: Dict[Tuple[int, int], Tuple[int, int, int]] = field(default_factory=dict)
    # Collectibles: set of cells that get added to `collected`.
    collectibles: FrozenSet[Tuple[int, int]] = frozenset()
    # Goal coset: the subset of group states that satisfy the exit condition.
    # Often just a single element {goal_state}, but can be a coset if the
    # exit accepts multiple equivalent configs.
    goal_predicate: Optional[callable] = None  # state -> bool


def apply_trigger(state: GroupState, delta: Tuple[int, int, int],
                   spec: GroupSpec) -> GroupState:
    dr, dc, ds = delta
    return GroupState(
        rotation=(state.rotation + dr) % spec.rot_mod,
        color=(state.color + dc) % spec.col_mod,
        shape=(state.shape + ds) % spec.shape_mod,
        collected=state.collected,
    )


def apply_collect(state: GroupState, cell: Tuple[int, int]) -> GroupState:
    return GroupState(
        rotation=state.rotation,
        color=state.color,
        shape=state.shape,
        collected=state.collected | {cell},
    )


@dataclass
class CrossingPlan:
    """How many times to cross each trigger, in what order."""
    trigger_order: List[Tuple[int, int]]  # sequence of trigger cells
    collectible_order: List[Tuple[int, int]]
    end_state: GroupState
    cost: int  # total number of crossings + collects


def plan_group_transitions(start: GroupState, spec: GroupSpec,
                             max_depth: int = 32
                             ) -> Optional[CrossingPlan]:
    """
    BFS on the Cayley graph of G. Generators = trigger deltas + collect ops.
    Finds the shortest sequence of crossings that lands in the goal coset.

    Returns a CrossingPlan specifying WHICH triggers to cross and HOW MANY
    times each. The potential field layer then routes through them.
    """
    if spec.goal_predicate and spec.goal_predicate(start):
        return CrossingPlan([], [], start, 0)

    q = deque([(start, [], [])])  # (state, trigger_seq, collect_seq)
    seen = {start.tup()}
    while q:
        state, tseq, cseq = q.popleft()
        if len(tseq) + len(cseq) > max_depth:
            continue
        # Try each trigger
        for cell, delta in spec.triggers.items():
            new_st = apply_trigger(state, delta, spec)
            if new_st.tup() in seen:
                continue
            seen.add(new_st.tup())
            new_tseq = tseq + [cell]
            if spec.goal_predicate and spec.goal_predicate(new_st):
                return CrossingPlan(new_tseq, cseq, new_st,
                                    len(new_tseq) + len(cseq))
            q.append((new_st, new_tseq, cseq))
        # Try each collectible (one-shot)
        for cell in spec.collectibles:
            if cell in state.collected:
                continue
            new_st = apply_collect(state, cell)
            if new_st.tup() in seen:
                continue
            seen.add(new_st.tup())
            new_cseq = cseq + [cell]
            if spec.goal_predicate and spec.goal_predicate(new_st):
                return CrossingPlan(tseq, new_cseq, new_st,
                                    len(tseq) + len(new_cseq))
            q.append((new_st, tseq, new_cseq))
    return None


def crossings_per_trigger(plan: CrossingPlan) -> Dict[Tuple[int, int], int]:
    """Aggregate: how many times each trigger cell needs to be crossed."""
    out: Dict[Tuple[int, int], int] = {}
    for cell in plan.trigger_order:
        out[cell] = out.get(cell, 0) + 1
    return out


def cayley_graph(spec: GroupSpec, start: GroupState, max_nodes: int = 5000
                  ) -> Dict[tuple, List[Tuple[str, tuple]]]:
    """Explicit Cayley graph around `start`. For debugging / visualization."""
    g: Dict[tuple, List[Tuple[str, tuple]]] = {}
    q = deque([start])
    seen = {start.tup()}
    while q and len(g) < max_nodes:
        s = q.popleft()
        edges = []
        for cell, delta in spec.triggers.items():
            ns = apply_trigger(s, delta, spec)
            edges.append((f"T{cell}", ns.tup()))
            if ns.tup() not in seen:
                seen.add(ns.tup())
                q.append(ns)
        g[s.tup()] = edges
    return g
