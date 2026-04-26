"""
Commutator analysis on a multiplication table.

For two actions a, b and a state s, the commutator is

    [a, b](s) = T_b(T_a(s)) ?= T_a(T_b(s))

If the equation holds for all s, the action pair is COMMUTATIVE — applying
them in either order yields the same world. If it FAILS at some state, then
hidden state is being manipulated in an order-dependent way.

The "non-commutative field" — the set of states where [a,b](s) breaks —
is geometrically informative: those are typically states near triggers,
where one action toggles a bit that the other action's behaviour depends on.

Outputs:

  - per-pair commutativity rate over visited states
  - list of states where each pair fails to commute
  - heuristic ranking of "trigger candidates" = pairs with low commutativity
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict
import numpy as np

from .multiplication_table import MultiplicationTable


@dataclass
class CommutatorReport:
    """Result of testing whether actions a, b commute over visited states."""
    a: str
    b: str
    n_tested: int        # states where both T_{ab}(s) and T_{ba}(s) are known
    n_commute: int       # of those, how many had T_{ab} = T_{ba}
    failing_states: List[bytes]   # states where commute failed

    @property
    def commute_rate(self) -> float:
        return self.n_commute / max(1, self.n_tested)

    @property
    def is_commutative(self) -> bool:
        return self.n_tested > 0 and self.n_commute == self.n_tested


def commute_pair(M: MultiplicationTable, a: str, b: str) -> CommutatorReport:
    """Test whether T_a and T_b commute on every state where both
    T_{ab}(s) and T_{ba}(s) can be computed from the table."""
    n_tested = 0
    n_commute = 0
    failing = []
    for s in M.states():
        sab = M.apply_word(s, a + b)
        sba = M.apply_word(s, b + a)
        if sab is None or sba is None:
            continue
        n_tested += 1
        if sab == sba:
            n_commute += 1
        else:
            failing.append(s)
    return CommutatorReport(a=a, b=b, n_tested=n_tested,
                             n_commute=n_commute, failing_states=failing)


def all_pairs(M: MultiplicationTable,
              generators: str = 'UDLR') -> Dict[Tuple[str, str], CommutatorReport]:
    """Compute commutator reports for every unordered pair."""
    out = {}
    seen = set()
    for a in generators:
        for b in generators:
            if a == b:
                continue
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            out[(a, b)] = commute_pair(M, a, b)
    return out


def commutator_matrix(M: MultiplicationTable,
                       generators: str = 'UDLR') -> np.ndarray:
    """|G| x |G| matrix of commute rates. Symmetric, diagonal = 1.0."""
    n = len(generators)
    mat = np.eye(n)
    for i, a in enumerate(generators):
        for j, b in enumerate(generators):
            if i == j:
                continue
            r = commute_pair(M, a, b)
            mat[i, j] = r.commute_rate
    return mat


def trigger_state_candidates(M: MultiplicationTable,
                              generators: str = 'UDLR') -> List[Tuple[bytes, int]]:
    """States that break MOST commutator pairs are candidates for trigger
    locations.  Each break = an action toggled hidden state."""
    breakage_count: Dict[bytes, int] = defaultdict(int)
    pairs = all_pairs(M, generators)
    for r in pairs.values():
        for s in r.failing_states:
            breakage_count[s] += 1
    out = sorted(breakage_count.items(), key=lambda x: -x[1])
    return out


def power_orders(M: MultiplicationTable,
                  generators: str = 'UDLR',
                  max_order: int = 8) -> Dict[Tuple[str, bytes], int]:
    """For each (action, state), find smallest k>0 with T_a^k(s) = s.

    k = 1: action bumps (fixed point).
    k = 2: action is involution at this state — applying twice returns home.
    k >= 3: longer cycle, suggests the action drives a counter."""
    out = {}
    for s in M.states():
        for a in generators:
            cur = s
            for k in range(1, max_order + 1):
                nxt = M.apply(cur, a)
                if nxt is None:
                    break
                if nxt == s:
                    out[(a, s)] = k
                    break
                cur = nxt
    return out
