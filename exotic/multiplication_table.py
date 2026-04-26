"""
Multiplication table for the action transformation semigroup.

Given a transformation log (sequence of (state, action) -> state observations),
we build the partial function

    M : State x Action -> State

where M[s][a] = T_a(s). When the underlying dynamics are deterministic, this
table fully describes the action of generators on the visited orbit.

From M we derive:

  - composition: T_{ab}(s) = M[M[s][a]][b]
  - orbit: BFS from start, applying all 4 generators
  - kernel words: words w with T_w(s_0) = s_0  (trivial sequences)
  - idempotents: actions a with T_a(s) = s for every s in orbit
  - reachability matrix: R[i][j] = 1 if state j reachable from state i

Determinism check: if we observe (s, a) -> s' and (s, a) -> s'' with s' != s'',
the dynamics are non-deterministic and the table records the most-frequent
transition while flagging non-determinism for that cell.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
from collections import defaultdict, deque
import numpy as np


@dataclass
class MultiplicationTable:
    """Partial function M : State x Action -> State."""
    # (sig, action) -> Counter of observed next sigs
    transitions: Dict[Tuple[bytes, str], Dict[bytes, int]] = field(default_factory=dict)
    # State labelling: short id assigned in order of first observation
    state_id: Dict[bytes, int] = field(default_factory=dict)

    def observe(self, sig_before: bytes, action: str, sig_after: bytes):
        if sig_before not in self.state_id:
            self.state_id[sig_before] = len(self.state_id)
        if sig_after not in self.state_id:
            self.state_id[sig_after] = len(self.state_id)
        key = (sig_before, action)
        self.transitions.setdefault(key, defaultdict(int))[sig_after] += 1

    # -- queries ------------------------------------------------------------
    def states(self) -> List[bytes]:
        """States in id order."""
        return sorted(self.state_id, key=self.state_id.get)

    def n_states(self) -> int:
        return len(self.state_id)

    def apply(self, sig: bytes, action: str) -> Optional[bytes]:
        """Most-frequently-observed T_a(sig). None if unseen."""
        key = (sig, action)
        d = self.transitions.get(key)
        if not d:
            return None
        return max(d, key=d.get)

    def apply_word(self, sig: bytes, word: str) -> Optional[bytes]:
        cur = sig
        for a in word:
            cur = self.apply(cur, a)
            if cur is None:
                return None
        return cur

    def is_deterministic_at(self, sig: bytes, action: str) -> Optional[bool]:
        """True iff (sig, action) has only one observed successor.
        None if (sig, action) was never observed."""
        d = self.transitions.get((sig, action))
        if not d:
            return None
        return len(d) == 1

    def determinism_score(self) -> float:
        """Fraction of (s,a) pairs that always go to the same s'."""
        if not self.transitions:
            return 1.0
        det = sum(1 for d in self.transitions.values() if len(d) == 1)
        return det / len(self.transitions)

    def coverage(self, generators: str = 'UDLR') -> float:
        """Fraction of (state, action) cells that are filled."""
        N = self.n_states()
        if N == 0:
            return 0.0
        denom = N * len(generators)
        filled = sum(1 for s in self.state_id
                     for a in generators if (s, a) in self.transitions)
        return filled / denom

    def fixed_points(self) -> Dict[str, Set[bytes]]:
        """For each action, set of states s where T_a(s) = s (action bumps)."""
        out: Dict[str, Set[bytes]] = defaultdict(set)
        for (s, a), d in self.transitions.items():
            top = max(d, key=d.get)
            if top == s:
                out[a].add(s)
        return dict(out)

    def orbit(self, start: bytes, generators: str = 'UDLR',
              max_depth: int = 50) -> Set[bytes]:
        """BFS-reachable states from start using the table."""
        seen = {start}; q = deque([start]); depth = 0
        while q and depth < max_depth:
            depth += 1
            nxt = deque()
            while q:
                s = q.popleft()
                for a in generators:
                    s2 = self.apply(s, a)
                    if s2 is not None and s2 not in seen:
                        seen.add(s2); nxt.append(s2)
            q = nxt
        return seen

    def shortest_word(self, src: bytes, dst: bytes,
                       generators: str = 'UDLR',
                       max_len: int = 30) -> Optional[str]:
        """BFS for the shortest word w with T_w(src) = dst."""
        if src == dst:
            return ''
        # (state, word_so_far)
        q = deque([(src, '')])
        seen = {src}
        while q:
            s, w = q.popleft()
            if len(w) >= max_len:
                continue
            for a in generators:
                s2 = self.apply(s, a)
                if s2 is None or s2 in seen:
                    continue
                if s2 == dst:
                    return w + a
                seen.add(s2)
                q.append((s2, w + a))
        return None

    def adjacency_matrix(self, generators: str = 'UDLR') -> np.ndarray:
        """Per-action 0/1 adjacency tensor of shape (|G|, N, N).
        a[g, i, j] = 1 iff T_{g}(state_i) = state_j."""
        N = self.n_states()
        ids = self.state_id
        A = np.zeros((len(generators), N, N), dtype=np.int8)
        for (s, a), d in self.transitions.items():
            top = max(d, key=d.get)
            if a not in generators or top not in ids:
                continue
            A[generators.index(a), ids[s], ids[top]] = 1
        return A

    def aggregated_adjacency(self, generators: str = 'UDLR') -> np.ndarray:
        """Sum across generators: weighted edge count between states."""
        return self.adjacency_matrix(generators).sum(axis=0)


# -----------------------------------------------------------------------------
# Building the table from rollout data
# -----------------------------------------------------------------------------

def build_from_log(log) -> MultiplicationTable:
    """log is a TransformationLog (from transformation_algebra)."""
    M = MultiplicationTable()
    for t in log.entries:
        M.observe(t.sig_before, t.action, t.sig_after)
    return M


# -----------------------------------------------------------------------------
# Cayley-style analyses
# -----------------------------------------------------------------------------

def compute_orbit_summary(M: MultiplicationTable, start: bytes
                           ) -> Dict:
    orbit = M.orbit(start)
    return {
        'orbit_size': len(orbit),
        'total_states_seen': M.n_states(),
        'orbit_completeness': len(orbit) / max(1, M.n_states()),
        'reachable_ids': sorted(M.state_id[s] for s in orbit),
    }


def detect_strongly_connected(M: MultiplicationTable,
                               generators: str = 'UDLR') -> List[Set[bytes]]:
    """Tarjan's SCC over the state-action graph."""
    states = M.states()
    sid = {s: i for i, s in enumerate(states)}
    adj = [[] for _ in states]
    for (s, a), d in M.transitions.items():
        top = max(d, key=d.get)
        if a in generators and s in sid and top in sid:
            adj[sid[s]].append(sid[top])

    index_counter = [0]
    stack = []
    on_stack = set()
    indices = {}
    lowlinks = {}
    sccs = []

    def strongconnect(v):
        indices[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v); on_stack.add(v)
        for w in adj[v]:
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])
        if lowlinks[v] == indices[v]:
            comp = set()
            while True:
                w = stack.pop(); on_stack.discard(w)
                comp.add(states[w])
                if w == v:
                    break
            sccs.append(comp)

    for v in range(len(states)):
        if v not in indices:
            strongconnect(v)
    return sccs
