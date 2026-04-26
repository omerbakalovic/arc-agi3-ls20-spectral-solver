"""
Transformation Algebra — actions as transformations of frame-space.

Different ontology from spatial analysis: instead of asking "where is
structure in the frame", we ask "what algebraic structure do the actions
induce on frame-space?"

Core objects:

  - Transformation T_a: F -> F' is the function induced by action a on
    a starting frame F. Concretely: T_a(F) = step(env reset to F, a).

  - Word w = a_1 a_2 ... a_n is a sequence of actions; induces composed
    transformation T_w = T_{a_n} o ... o T_{a_1}.

  - Commutator [a, b] = a b a^{-1} b^{-1} measures whether a and b commute.
    For grid maze with no triggers, [U, D] = identity. Non-trivial commutator
    => actions modify hidden state (counter, switch, key).

  - Orbit of a state s under generators G is {T_w(s) : w in G*}.
    Orbit size = number of distinct reachable states. For solvable level,
    orbit must contain at least one state with levels_completed > 0.

  - Invariant of group action: pixel set I subset Z^2 such that every
    transformation preserves the COLOR distribution on I. Static walls
    are invariant; player and triggers are not.

We use this to:
  1. Detect non-commutativity => identifies actions/states that touch
     hidden machinery (likely triggers).
  2. Find invariants => filter perception to "structure-only" pixels.
  3. Build state-action graph (Cayley-like) => analyze topology of
     state space, not just spatial topology.

This is mathematics-of-actions instead of mathematics-of-space.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set, Callable
import numpy as np
import hashlib


# -----------------------------------------------------------------------------
#  State signatures
# -----------------------------------------------------------------------------

def frame_signature(frame: np.ndarray, hud_cutoff: int = 55) -> bytes:
    """Hash of the play-area pixels — game state fingerprint.

    Two frames have the same signature iff they look identical above
    the HUD. We use this as the equivalence class for state-space
    reasoning. A small h(F) collision rate is acceptable; signatures
    do not need to be cryptographic.
    """
    return hashlib.md5(frame[:hud_cutoff, :].tobytes()).digest()


def player_aware_signature(frame: np.ndarray,
                            hud_cutoff: int = 55,
                            player_color: int = 12) -> bytes:
    """Signature that ignores the player sprite — useful for asking
    'is the WORLD in the same state' (regardless of player position)."""
    f = frame[:hud_cutoff, :].copy()
    f[f == player_color] = 0   # mask player pixels uniformly
    return hashlib.md5(f.tobytes()).digest()


# -----------------------------------------------------------------------------
#  Transformation log
# -----------------------------------------------------------------------------

@dataclass
class Transformation:
    """A single observed (state, action) -> next state."""
    action: str
    sig_before: bytes
    sig_after: bytes
    pos_before: Optional[Tuple[int, int]]
    pos_after: Optional[Tuple[int, int]]
    world_changed: bool          # sig differs ignoring player
    moved: bool                  # player moved
    levels_completed_before: int
    levels_completed_after: int


@dataclass
class TransformationLog:
    """Append-only history of all observed transformations.

    Lets us answer questions like:
      - 'Which (sig, action) pairs ever changed the world?'
      - 'Did U and D commute from this state?'
      - 'What is the orbit reachable from initial state?'
    """
    entries: List[Transformation] = field(default_factory=list)

    def record(self, t: Transformation):
        self.entries.append(t)

    def world_changing_actions(self) -> List[Transformation]:
        return [t for t in self.entries if t.world_changed]

    def state_action_table(self) -> Dict[bytes, Dict[str, bytes]]:
        """For each visited state, which next-state did each action lead to?"""
        table: Dict[bytes, Dict[str, bytes]] = {}
        for t in self.entries:
            table.setdefault(t.sig_before, {})[t.action] = t.sig_after
        return table

    def visited_states(self) -> Set[bytes]:
        s: Set[bytes] = set()
        for t in self.entries:
            s.add(t.sig_before); s.add(t.sig_after)
        return s


# -----------------------------------------------------------------------------
#  Commutator analysis
# -----------------------------------------------------------------------------

def commutator_test(driver: 'TransformationDriver',
                     start_sig: bytes,
                     a: str, b: str) -> Tuple[bool, bytes, bytes]:
    """Test whether actions a and b commute from state start_sig.

    Returns (commutes, sig_after_ab, sig_after_ba). The driver is
    responsible for restoring the environment to start_sig before each
    word. Most ls20-style envs lack reset-to-state, so this can only
    be applied opportunistically to the SAME starting frame collected
    via independent rollouts.
    """
    sig_ab = driver.apply_word(start_sig, a + b)
    sig_ba = driver.apply_word(start_sig, b + a)
    if sig_ab is None or sig_ba is None:
        return False, sig_ab or b'', sig_ba or b''
    return sig_ab == sig_ba, sig_ab, sig_ba


# -----------------------------------------------------------------------------
#  Invariant detection
# -----------------------------------------------------------------------------

def pixel_invariants(frames: List[np.ndarray],
                     hud_cutoff: int = 55) -> np.ndarray:
    """Boolean mask: True where pixel value is CONSTANT across all frames.

    The invariant set is the static structure of the level (walls,
    decorations). Anything not invariant changes — either because
    the player moved or because the world changed.

    Run this on a list of frames sampled across many actions to get
    the "structural skeleton" — pixels that nothing moves.
    """
    if not frames:
        return np.zeros((1, 1), dtype=bool)
    stack = np.stack([f[:hud_cutoff, :] for f in frames])  # (T, H, W)
    invariant = (stack == stack[0]).all(axis=0)
    return invariant


def cell_invariance_score(frames: List[np.ndarray],
                           cell_size: int = 5,
                           col_offset: int = 4,
                           hud_cutoff: int = 55
                           ) -> Dict[Tuple[int, int], float]:
    """Per-grid-cell invariance score in [0, 1]. 1.0 = never changes.

    Cells with intermediate scores (0.3 - 0.9) are MORE INTERESTING
    than fully invariant or fully-moving cells: they imply rare
    triggered events, which are likely the trigger machinery itself.
    """
    if not frames:
        return {}
    stack = np.stack([f[:hud_cutoff, :] for f in frames]).astype(int)
    H, W = stack.shape[1], stack.shape[2]
    scores: Dict[Tuple[int, int], float] = {}
    for r in range(0, hud_cutoff, cell_size):
        if r + cell_size > hud_cutoff:
            continue
        for c in range(col_offset, W - cell_size + 1, cell_size):
            block = stack[:, r:r+cell_size, c:c+cell_size]   # (T, 5, 5)
            # fraction of pixels that match block at t=0
            same = (block == block[0:1]).mean()
            scores[(r, c)] = float(same)
    return scores


# -----------------------------------------------------------------------------
#  Symmetry detection
# -----------------------------------------------------------------------------

def detect_axial_symmetries(frame: np.ndarray,
                              hud_cutoff: int = 55,
                              player_color: int = 12) -> Dict[str, float]:
    """Returns symmetry scores for vertical/horizontal flips and 180-rot.

    Score = fraction of pixels that match under the symmetry. We mask
    out the player sprite first since it usually breaks symmetry.

    Levels with high symmetry (> 0.85) suggest mirror-image puzzle
    structure; actions that BREAK symmetry are then meaningful.
    """
    f = frame[:hud_cutoff, :].copy()
    f[f == player_color] = -1   # mark player to ignore
    valid = (f != -1)

    def score(g):
        match = (f == g) & valid & (g != -1)
        n = valid.sum()
        return float(match.sum()) / max(1, int(n))

    return {
        'vertical_flip':   score(np.fliplr(f)),
        'horizontal_flip': score(np.flipud(f)),
        'rot_180':         score(np.flipud(np.fliplr(f))),
    }


# -----------------------------------------------------------------------------
#  Action effect classifier
# -----------------------------------------------------------------------------

@dataclass
class ActionEffect:
    """Statistics about what a particular action tends to do."""
    action: str
    n_observations: int = 0
    n_moved: int = 0              # player moved
    n_world_changed: int = 0      # world signature changed
    n_levelup: int = 0            # caused level completion
    n_died: int = 0


def classify_action_effects(log: TransformationLog) -> Dict[str, ActionEffect]:
    """Aggregate per-action statistics from the log."""
    out: Dict[str, ActionEffect] = {}
    for t in log.entries:
        e = out.setdefault(t.action, ActionEffect(action=t.action))
        e.n_observations += 1
        if t.moved: e.n_moved += 1
        if t.world_changed: e.n_world_changed += 1
        if t.levels_completed_after > t.levels_completed_before:
            e.n_levelup += 1
        if t.pos_after is None and t.pos_before is not None:
            e.n_died += 1
    return out


# -----------------------------------------------------------------------------
#  Driver protocol  (concrete impls live in experiment scripts)
# -----------------------------------------------------------------------------

class TransformationDriver:
    """Abstract interface — collects transformations from an environment.

    Concrete drivers handle env reset/replay so that the algebra layer
    can request 'apply word w to state s' regardless of game capability.
    """
    def apply_word(self, start_sig: bytes, word: str) -> Optional[bytes]:
        raise NotImplementedError

    def random_walk(self, n_steps: int) -> TransformationLog:
        raise NotImplementedError
