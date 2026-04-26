"""
State-machine solver — robust orchestration for the exotic stack.

States:
  NAVIGATE          — descend potential field toward best target
  ENTER_EXIT        — at exit candidate, try to push through (exit may
                      look like a wall from our walkability heuristic)
  PROBE_LOCAL       — plateaued; poke each blocked direction adjacent to us
  EXPLORE           — no local switch; BFS to every unvisited walkable cell
                      and poke blocked directions from each
  REPLAN            — walkable set changed; re-perceive and pick new target
  DONE / STUCK      — terminal

Invariants:
  * Floor colors detected ONCE at start and cached (stable perception).
  * We never repeat the same (state, pos, walkable_sig, target) triple —
    prevents infinite loops.
  * Every "poke" that might die is treated as last resort.

Pattern-agnostic: no game-specific constants. Works across games that fit
the "grid maze + doors + triggers + exit" template.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable, Set
from collections import deque
import os, pickle
import numpy as np

from scipy.ndimage import laplace as _ndlap
from collections import defaultdict

from .perception import perceive, auto_floor_colors, PerceptionResult
from .tda import compute_tda, classify_level
from .potential_field import FieldSpec, solve_laplace, PotentialField
from .dynamics_probe import detect_player_pos
from .temporal_diff import frame_diff_events, summarize_events, is_progress, DiffEvent


CELL = 5
DELTA4_XY = [(-CELL, 0), (CELL, 0), (0, -CELL), (0, CELL)]


def laplacian_trigger_prior(frame: np.ndarray,
                             walkable: Set[Tuple[int, int]],
                             play_rows: int = 55) -> List[Tuple[Tuple[int, int], float]]:
    """
    For each cell NOT in walkable but adjacent to walkable, compute
    z-score of its |Δf| energy against cells of the same dominant color.

    Returns a list of (cell, z_score) sorted by z_score descending.
    Cells with anomalously high curvature energy are more likely to be
    interactive (triggers / switches / exit-doors).
    """
    lap = np.abs(_ndlap(frame.astype(float)))
    rows = list(range(0, play_rows, CELL))
    cols = list(range(4, frame.shape[1] - CELL + 1, CELL))

    E, dom = {}, {}
    for r in rows:
        for c in cols:
            E[(r, c)] = float(lap[r:r+CELL, c:c+CELL].sum())
            block = frame[r:r+CELL, c:c+CELL].astype(int)
            dom[(r, c)] = int(np.bincount(block.flatten(), minlength=16).argmax())

    groups = defaultdict(list)
    for k, v in E.items():
        groups[dom[k]].append(v)
    mu_std = {color: (float(np.mean(vals)), float(np.std(vals)) + 1e-6)
              for color, vals in groups.items()}

    out = []
    for (r, c), e in E.items():
        if (r, c) in walkable:
            continue
        adj = sum(1 for dr, dc in DELTA4_XY if (r+dr, c+dc) in walkable)
        if adj == 0:
            continue
        mu, sd = mu_std[dom[(r, c)]]
        z = (e - mu) / sd
        out.append(((r, c), z))
    out.sort(key=lambda t: -t[1])
    return out


DELTA = {'U': (-5, 0), 'D': (5, 0), 'L': (0, -5), 'R': (0, 5)}


class SMState:
    NAVIGATE      = 'NAVIGATE'
    ENTER_EXIT    = 'ENTER_EXIT'
    PROBE_LOCAL   = 'PROBE_LOCAL'
    EXPLORE       = 'EXPLORE'
    FIND_TRIGGER  = 'FIND_TRIGGER'   # target is locked; hunt for its opener
    GLOBAL_HUNT   = 'GLOBAL_HUNT'    # last resort: try every high-z cell on map
    REPLAN        = 'REPLAN'
    DONE          = 'DONE'
    STUCK         = 'STUCK'


def walkable_sig(pr: PerceptionResult,
                  exclude: Optional[Set[Tuple[int, int]]] = None) -> frozenset:
    """Stable walkable signature ignoring player-shadow noise."""
    s = set(pr.grid_walkable)
    if exclude:
        s -= exclude
    return frozenset(s)


def bfs_path(walkable, start, goal):
    q = deque([(start, [])])
    seen = {start}
    while q:
        pos, path = q.popleft()
        if pos == goal:
            return path
        for a, (dr, dc) in DELTA.items():
            nb = (pos[0]+dr, pos[1]+dc)
            if nb in walkable and nb not in seen:
                seen.add(nb)
                q.append((nb, path + [a]))
    return None


def find_exit_candidates(pr: PerceptionResult,
                          player_pos: Tuple[int, int],
                          floor_colors: Optional[Set[int]] = None,
                          wall_colors: Optional[Set[int]] = None) -> List[dict]:
    """
    Ranked candidates for "the exit". Exit tends to:
      * be a small entity (15-100 px) NOT floor and NOT the dominant wall
      * have >=1 walkable neighbour (reachable)
      * sit far from player
      * not be in HUD
    Wall colors are detected as the most-populous non-floor non-player color.
    """
    floor_colors = floor_colors or set()
    if wall_colors is None:
        wall_colors = set()
        play = pr.frame[:55, :]
        counts = {}
        for c in np.unique(play):
            ci = int(c)
            if ci == 12 or ci in floor_colors:
                continue
            counts[ci] = int((play == ci).sum())
        if counts:
            wall_colors = {max(counts, key=counts.get)}
    out = []
    for e in pr.entities:
        if e.color == 12 or not e.grid_cells:
            continue
        if e.color in floor_colors or e.color in wall_colors:
            continue
        if e.area < 12 or e.area > 100:
            continue
        best_cell, best_nb = None, 0
        for c in e.grid_cells:
            if c[0] >= 50 or c == player_pos:
                continue
            nb = sum(1 for dr, dc in DELTA.values()
                     if (c[0]+dr, c[1]+dc) in pr.grid_walkable)
            if nb > best_nb:
                best_nb, best_cell = nb, c
        if best_cell is None:
            continue
        dist = abs(best_cell[0]-player_pos[0]) + abs(best_cell[1]-player_pos[1])
        out.append({
            'cell': best_cell, 'entity': e, 'adj': best_nb, 'dist': dist,
            'color': e.color, 'area': e.area,
        })
    out.sort(key=lambda d: (-d['adj'], -d['dist']))
    return out


@dataclass
class SMConfig:
    max_outer_iterations: int = 50
    max_nav_steps: int = 40
    max_explore_pokes: int = 60
    player_color: int = 12
    verbose: bool = True
    # Baseline level completion count at start (used to detect progress
    # against levels already cleared via skip).
    starting_level: int = 0
    # Persistent danger-map: remember cells where the player died across runs
    danger_map_path: Optional[str] = None   # e.g. 'danger_l1.pkl'
    danger_blast_radius: int = 2            # mark N cells of the pre-death path
    # Persistent active-walkability calibration
    walkability_path: Optional[str] = None  # e.g. 'walk_l2.pkl'


@dataclass
class SMSolver:
    env_step: Callable                 # (action_char) -> step_result
    get_last_frame: Callable           # () -> np.ndarray
    cfg: SMConfig = field(default_factory=SMConfig)

    # runtime state
    floor_colors: Optional[Set[int]] = None
    current_frame: Optional[np.ndarray] = None
    prev_frame: Optional[np.ndarray] = None
    history: List[str] = field(default_factory=list)
    visited_switch_probe: Set[Tuple[Tuple[int,int], str]] = field(default_factory=set)
    dead_cells: Set[Tuple[int,int]] = field(default_factory=set)
    dead_targets: Set[Tuple[int,int]] = field(default_factory=set)
    # Cells that LOOK walkable (floor color) but the player can't enter.
    # Learned actively from bumps. Persistent within run; can be saved.
    pseudo_walls: Set[Tuple[int,int]] = field(default_factory=set)
    # Cells the player has actually OCCUPIED during this run — empirical
    # walkability ground truth. Always trusted over color heuristic.
    confirmed_walkable: Set[Tuple[int,int]] = field(default_factory=set)
    locked_targets: Set[Tuple[int,int]] = field(default_factory=set)
    lock_attempts: Dict[Tuple[int,int], int] = field(default_factory=dict)
    # Persistent: cells to treat as hazards in the Laplace field
    danger_cells: Set[Tuple[int,int]] = field(default_factory=set)
    # Recent trail of (pos, action) — blame these on death
    recent_trail: List[Tuple[Tuple[int,int], str]] = field(default_factory=list)

    def log(self, msg: str):
        if self.cfg.verbose:
            print(msg)
        self.history.append(msg)

    def step(self, action: str) -> Tuple[Optional[np.ndarray], int]:
        # Snapshot pos before step for active calibration
        pre_pos = self.pos()
        r = self.env_step(action)
        frame = None
        try:
            if r.frame and len(r.frame) > 0:
                frame = np.array(r.frame[0])
        except Exception:
            frame = None
        lvl = int(getattr(r, 'levels_completed', 0))
        self.prev_frame = self.current_frame
        self.current_frame = frame
        # Active walkability calibration
        if frame is not None and pre_pos is not None:
            post_pos = detect_player_pos(frame, self.cfg.player_color)
            if post_pos is not None:
                self.confirmed_walkable.add(post_pos)
                if post_pos == pre_pos:
                    # Bumped — destination is a pseudo-wall
                    dr, dc = DELTA[action]
                    self.pseudo_walls.add((pre_pos[0]+dr, pre_pos[1]+dc))
                else:
                    # Moved — clear any false pseudo-wall mark on destination
                    self.pseudo_walls.discard(post_pos)
        return frame, lvl

    def events_since_last_step(self, player_pos_hint=None) -> List[DiffEvent]:
        if self.prev_frame is None or self.current_frame is None:
            return []
        return frame_diff_events(self.prev_frame, self.current_frame,
                                  floor_colors=self.floor_colors or set(),
                                  player_color=self.cfg.player_color,
                                  player_pos=player_pos_hint)

    def perceive_now(self) -> Optional[PerceptionResult]:
        if self.current_frame is None:
            return None
        return perceive(self.current_frame, floor_colors=self.floor_colors)

    def pos(self) -> Optional[Tuple[int, int]]:
        return detect_player_pos(self.current_frame, self.cfg.player_color) \
               if self.current_frame is not None else None

    def _player_alive(self, frame) -> bool:
        """Quick check — is the player sprite still on the frame?"""
        if frame is None:
            return False
        return detect_player_pos(frame, self.cfg.player_color) is not None

    def _load_walkability(self):
        p = self.cfg.walkability_path
        if p and os.path.exists(p):
            try:
                with open(p, 'rb') as f:
                    d = pickle.load(f)
                self.pseudo_walls = set(d.get('pseudo_walls', set()))
                self.confirmed_walkable = set(d.get('confirmed', set()))
                self.log(f"[walk-calib] loaded pseudo={len(self.pseudo_walls)} "
                         f"confirmed={len(self.confirmed_walkable)} from {p}")
            except Exception as e:
                self.log(f"[walk-calib] load failed: {e}")

    def _save_walkability(self):
        p = self.cfg.walkability_path
        if not p: return
        try:
            with open(p, 'wb') as f:
                pickle.dump({'pseudo_walls': self.pseudo_walls,
                             'confirmed': self.confirmed_walkable}, f)
        except Exception as e:
            self.log(f"[walk-calib] save failed: {e}")

    def _load_danger(self):
        p = self.cfg.danger_map_path
        if p and os.path.exists(p):
            try:
                with open(p, 'rb') as f:
                    self.danger_cells = set(pickle.load(f))
                self.log(f"[danger] loaded {len(self.danger_cells)} cells from {p}")
            except Exception as e:
                self.log(f"[danger] load failed: {e}")

    def _save_danger(self):
        p = self.cfg.danger_map_path
        if not p: return
        try:
            with open(p, 'wb') as f:
                pickle.dump(self.danger_cells, f)
            self.log(f"[danger] saved {len(self.danger_cells)} cells to {p}")
        except Exception as e:
            self.log(f"[danger] save failed: {e}")

    def _remember_death(self, pos_before: Optional[Tuple[int,int]],
                        last_action: Optional[str]):
        """Blame death on recent trail + the cell we tried to step into."""
        r = self.cfg.danger_blast_radius
        if pos_before is not None and last_action is not None:
            dr, dc = DELTA[last_action]
            target = (pos_before[0]+dr, pos_before[1]+dc)
            self.danger_cells.add(target)
        # Add tail of recent trail (closer to death = more certain)
        for (p, _a) in self.recent_trail[-r:]:
            self.danger_cells.add(p)
        self._save_danger()
        self._save_walkability()

    def _trail_push(self, pos, action):
        self.recent_trail.append((pos, action))
        if len(self.recent_trail) > 12:
            self.recent_trail.pop(0)

    def _classify_delta(self, cur_sig, sig_now, frame, lvl) -> str:
        """Return one of: 'death', 'switch', 'noise', 'level'."""
        if lvl > self.cfg.starting_level:
            return 'level'
        if not self._player_alive(frame):
            return 'death'
        dp = len(sig_now - cur_sig); dm = len(cur_sig - sig_now)
        # Asymmetric large shrink w/ player alive but off-screen = usually death
        if dm >= 10 and dp == 0:
            return 'death'
        # Player-shadow is near-symmetric (+k/-k). Real events are asymmetric.
        # Pickup: +1/0 or +2/0 — a small opening appeared where something was.
        # Switch: larger asymmetric changes.
        if max(dp, dm) >= 5 or abs(dp - dm) >= 3:
            return 'switch'
        # Asymmetric positive with minimal negative = pickup/door-open
        if dp >= 1 and dm <= 1 and (dp - dm) >= 1:
            return 'switch'
        return 'noise'

    def solve(self, starting_frame: np.ndarray) -> bool:
        """Run until level completed, player dies, or we give up."""
        self.current_frame = starting_frame
        self.floor_colors = auto_floor_colors(starting_frame)
        self.log(f"[init] floor_colors={self.floor_colors}")
        self._load_danger()
        self._load_walkability()

        state = SMState.NAVIGATE
        target: Optional[dict] = None
        last_walk_sig: Optional[frozenset] = None
        seen_situations: Set[tuple] = set()
        steps_total = 0

        for outer in range(self.cfg.max_outer_iterations):
            pr = self.perceive_now()
            if pr is None:
                self.log("[halt] no frame")
                return False
            pos = self.pos()
            if pos is None:
                self.log("[halt] no player pos")
                return False
            # Exclude a disc around player from walkable signature to kill
            # shadow noise. Shadow occupies roughly the cell at pos.
            shadow_mask = {pos, (pos[0]-5, pos[1]), (pos[0]+5, pos[1]),
                           (pos[0], pos[1]-5), (pos[0], pos[1]+5)}
            cur_sig = walkable_sig(pr, exclude=shadow_mask)

            # Detect world change -> force REPLAN (must be a real change,
            # not just player moving)
            if last_walk_sig is not None and cur_sig != last_walk_sig:
                delta_plus = len(cur_sig - last_walk_sig)
                delta_minus = len(last_walk_sig - cur_sig)
                # Small symmetric deltas (+k -k where k<=2) are usually shadow
                if max(delta_plus, delta_minus) >= 5 or abs(delta_plus - delta_minus) >= 3:
                    self.log(f"[replan] walkable changed: +{delta_plus} -{delta_minus}")
                    state = SMState.REPLAN
            last_walk_sig = cur_sig

            # Infinite-loop guard
            situation = (state, pos, cur_sig, target['cell'] if target else None)
            if situation in seen_situations and state == SMState.NAVIGATE:
                self.log(f"[loop-guard] seen situation before -> EXPLORE")
                state = SMState.EXPLORE
            seen_situations.add(situation)

            self.log(f"\n[outer {outer}] state={state} pos={pos} walk={len(pr.grid_walkable)}")

            # REPLAN
            if state == SMState.REPLAN:
                cands = [c for c in find_exit_candidates(pr, pos, floor_colors=self.floor_colors)
                         if c['cell'] not in self.dead_targets]
                if not cands:
                    self.log("  [replan] no exit candidates — EXPLORE")
                    state = SMState.EXPLORE
                    continue
                target = cands[0]
                self.log(f"  [replan] target={target['cell']} c={target['color']} adj={target['adj']}")
                state = SMState.NAVIGATE
                continue

            # Pick initial target only if we don't have one and we want to NAVIGATE
            if target is None and state == SMState.NAVIGATE:
                cands = [c for c in find_exit_candidates(pr, pos, floor_colors=self.floor_colors)
                         if c['cell'] not in self.dead_targets]
                if cands:
                    target = cands[0]
                    self.log(f"  [target] {target['cell']} c={target['color']}")
                else:
                    self.log("  [target] none — fallthrough EXPLORE")
                    state = SMState.EXPLORE

            # Transition: on or adjacent to target -> try to enter exit (ONCE per target)
            if state == SMState.NAVIGATE and target:
                cr, cc = target['cell']
                dist = abs(pos[0]-cr) + abs(pos[1]-cc)
                tried_key = ('enter', target['cell'])
                if dist <= 5 and tried_key not in self.visited_switch_probe:
                    self.visited_switch_probe.add(tried_key)
                    state = SMState.ENTER_EXIT

            # === MATH-PRIOR PRE-NAVIGATE COLLECTION ===
            # If an anomalously-high-z cell is adjacent to player AND not
            # already probed, poke it first. This catches "grab key before
            # heading to exit"-type patterns geometrically.
            if state == SMState.NAVIGATE and target is not None:
                prior_cells = dict(laplacian_trigger_prior(pr.frame, pr.grid_walkable))
                best_a, best_z, best_nb = None, -1e9, None
                for a, (dr, dc) in DELTA.items():
                    nb = (pos[0]+dr, pos[1]+dc)
                    z = prior_cells.get(nb, -1e9)
                    key = (pos, a)
                    if z > best_z and z >= 1.0 and key not in self.visited_switch_probe:
                        best_z, best_a, best_nb = z, a, nb
                if best_a is not None:
                    self.log(f"  [pre-collect] poke {best_a} into {best_nb} z={best_z:+.2f}")
                    self.visited_switch_probe.add((pos, best_a))
                    self._trail_push(pos, best_a)
                    frame, lvl = self.step(best_a); steps_total += 1
                    if frame is None:
                        self._remember_death(pos, best_a); return False
                    if lvl > self.cfg.starting_level:
                        self.log(f"*** SOLVED via pre-collect ***"); return True
                    p2 = detect_player_pos(frame)
                    if p2 is None:
                        self.log(f"  [pre-collect] DIED"); self._remember_death(pos, best_a); return False
                    pr_now = perceive(frame, floor_colors=self.floor_colors)
                    shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                    (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                    sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                    kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                    dp = len(sig_now - cur_sig); dm = len(cur_sig - sig_now)
                    # Temporal-diff: did an ENTITY-level event occur?
                    evs = self.events_since_last_step(player_pos_hint=pos)
                    if evs:
                        self.log(f"  [pre-collect] events: {summarize_events(evs[:3])}")
                    progress_ev = is_progress(evs)
                    self.log(f"  [pre-collect] delta +{dp}/-{dm} kind={kind} progress_ev={progress_ev}")
                    if kind in ('switch', 'level') or progress_ev:
                        # Unlock any previously locked targets — they may be open
                        for lc in list(self.locked_targets):
                            self.locked_targets.discard(lc)
                        for lc in list(self.visited_switch_probe):
                            if isinstance(lc, tuple) and lc and lc[0] == 'enter':
                                self.visited_switch_probe.discard(lc)
                        self.log(f"  [pre-collect] world changed -> REPLAN")
                        state = SMState.REPLAN
                        continue
                    # no change — fall through to normal NAVIGATE

            # NAVIGATE
            if state == SMState.NAVIGATE:
                # Always include player position + target in walkable —
                # player cell often misses floor-color heuristic due to
                # sprite/shadow domination.
                walkable = (pr.grid_walkable | self.confirmed_walkable
                            | {target['cell'], pos}) - self.pseudo_walls
                walkable.add(pos)  # never exclude actual player cell
                self.log(f"  [nav-debug] |walk|={len(walkable)}, "
                         f"pseudo_walls={len(self.pseudo_walls)}, "
                         f"confirmed={len(self.confirmed_walkable)}")
                pf = solve_laplace(FieldSpec(walkable=walkable,
                                              exit_cell=target['cell'],
                                              hazards=set(self.danger_cells)),
                                     max_iters=2000)
                cur = pos
                moved_anything = False
                for nav_i in range(self.cfg.max_nav_steps):
                    a = pf.action_at(cur)
                    if a is None:
                        self.log(f"  [nav-debug] no descent from {cur} at step {nav_i}")
                        break
                    self.log(f"  [nav-step {nav_i}] {cur} -> action={a}")
                    pos_before = cur
                    self._trail_push(cur, a)
                    frame, lvl = self.step(a); steps_total += 1
                    if frame is None:
                        self.log(f"  [died] during nav")
                        self._remember_death(pos_before, a); return False
                    if lvl > self.cfg.starting_level:
                        self.log(f"*** LEVEL COMPLETED at step {steps_total} ***")
                        return True
                    new_pos = detect_player_pos(frame)
                    if new_pos is None:
                        self.log("  [nav] player lost")
                        self._remember_death(pos_before, a); return False
                    if new_pos == cur:
                        # bumped wall — record what we tried to step into
                        dr, dc = DELTA[a]
                        bumped_cell = (cur[0]+dr, cur[1]+dc)
                        if bumped_cell not in self.pseudo_walls:
                            self.pseudo_walls.add(bumped_cell)
                            self.log(f"  [calib] bumped at {bumped_cell} via {a} -> pseudo-wall")
                        break
                    cur = new_pos
                    moved_anything = True
                    # Check walkable change (ignoring shadow noise)
                    pr_now = perceive(frame, floor_colors=self.floor_colors)
                    shadow_mask2 = {new_pos,
                                    (new_pos[0]-5, new_pos[1]),
                                    (new_pos[0]+5, new_pos[1]),
                                    (new_pos[0], new_pos[1]-5),
                                    (new_pos[0], new_pos[1]+5)}
                    sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                    dp = len(sig_now - cur_sig)
                    dm = len(cur_sig - sig_now)
                    if max(dp, dm) >= 5 or abs(dp - dm) >= 3:
                        self.log(f"  [nav] walkable changed mid-nav +{dp}/-{dm}")
                        state = SMState.REPLAN
                        break
                if state == SMState.NAVIGATE:
                    cr, cc = target['cell']
                    dist = abs(cur[0]-cr) + abs(cur[1]-cc)
                    tried_key = ('enter', target['cell'])
                    if cur == target['cell'] or (dist <= 5 and tried_key not in self.visited_switch_probe):
                        self.visited_switch_probe.add(tried_key)
                        state = SMState.ENTER_EXIT
                    else:
                        state = SMState.PROBE_LOCAL
                continue

            # ENTER_EXIT: at exit cell, push through
            if state == SMState.ENTER_EXIT:
                self.log("  [enter] trying to push through exit")
                for a in ['U', 'L', 'R', 'D']:
                    frame, lvl = self.step(a); steps_total += 1
                    if frame is None:
                        return False
                    if lvl > self.cfg.starting_level:
                        self.log(f"*** SOLVED via direct push {a} ***")
                        return True
                    pr_now = perceive(frame, floor_colors=self.floor_colors)
                    p2 = detect_player_pos(frame)
                    if p2 is None:
                        self.log(f"  [enter] push {a} — PLAYER DIED")
                        self._remember_death(pos, a); return False
                    shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                    (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                    sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                    kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                    if kind == 'death':
                        self.log(f"  [enter] push {a} death-like; abort")
                        self._remember_death(pos, a); return False
                    if kind == 'switch':
                        dp = len(sig_now-cur_sig); dm = len(cur_sig-sig_now)
                        self.log(f"  [enter] push {a} changed world +{dp}/-{dm}")
                        state = SMState.REPLAN
                        break
                else:
                    # Exit cell didn't accept push — treat as LOCKED, hunt trigger
                    if target is not None:
                        cell = target['cell']
                        n = self.lock_attempts.get(cell, 0) + 1
                        self.lock_attempts[cell] = n
                        if n >= 3:
                            self.dead_targets.add(cell)
                            self.log(f"  [enter] target {cell} permanently dead after {n}")
                            target = None
                            state = SMState.REPLAN
                        else:
                            self.locked_targets.add(cell)
                            self.log(f"  [enter] target {cell} LOCKED (attempt {n}) — FIND_TRIGGER")
                            state = SMState.FIND_TRIGGER
                    else:
                        state = SMState.PROBE_LOCAL
                continue

            # PROBE_LOCAL — poke ALL 4 directions (don't trust walkable mask)
            if state == SMState.PROBE_LOCAL:
                self.log(f"  [probe-local] at {pos}")
                changed = False
                for a, (dr, dc) in DELTA.items():
                    key = (pos, a)
                    if key in self.visited_switch_probe:
                        continue
                    self.visited_switch_probe.add(key)
                    frame, lvl = self.step(a); steps_total += 1
                    if frame is None: return False
                    if lvl > self.cfg.starting_level:
                        self.log(f"*** SOLVED via probe push {a} ***")
                        return True
                    pr_now = perceive(frame, floor_colors=self.floor_colors)
                    p2 = detect_player_pos(frame)
                    if p2 is None:
                        self.log(f"  [probe-local] {a} — PLAYER DIED")
                        self._remember_death(pos, a); return False
                    shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                    (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                    sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                    kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                    if kind == 'death':
                        self.log(f"  [probe-local] {a} death-like; abort")
                        self._remember_death(pos, a); return False
                    if kind == 'switch':
                        dp = len(sig_now-cur_sig); dm = len(cur_sig-sig_now)
                        self.log(f"  [probe-local] {a} changed world +{dp}/-{dm}")
                        state = SMState.REPLAN
                        changed = True
                        break
                if not changed:
                    state = SMState.EXPLORE
                continue

            # EXPLORE
            if state == SMState.EXPLORE:
                self.log("  [explore] walking walkable, poking walls")
                changed = False
                # Prioritize cells NOT probed yet
                candidates = [c for c in pr.grid_walkable
                              if any((c, a) not in self.visited_switch_probe
                                     for a in DELTA)]
                candidates.sort(key=lambda c: abs(c[0]-pos[0])+abs(c[1]-pos[1]))
                pokes = 0
                for target_cell in candidates:
                    if pokes >= self.cfg.max_explore_pokes:
                        break
                    if pos is None:
                        break
                    safe_walk = (pr.grid_walkable | {pos}) - self.danger_cells - self.pseudo_walls
                    path = bfs_path(safe_walk, pos, target_cell)
                    if path is None:
                        continue
                    # walk there
                    died = False
                    for a in path:
                        frame, lvl = self.step(a); steps_total += 1
                        if frame is None: died = True; break
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** SOLVED during explore-walk ***")
                            return True
                    if died: return False
                    pos = self.pos()
                    if pos is None:
                        continue
                    # poke all 4 directions (trust nothing)
                    for a, (dr, dc) in DELTA.items():
                        key = (pos, a)
                        if key in self.visited_switch_probe:
                            continue
                        self.visited_switch_probe.add(key)
                        frame, lvl = self.step(a); steps_total += 1
                        pokes += 1
                        if frame is None: return False
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** SOLVED via explore-poke ***")
                            return True
                        pr_now = perceive(frame, floor_colors=self.floor_colors)
                        p2 = detect_player_pos(frame)
                        if p2 is None:
                            self.log(f"  [explore] poke at {pos} {a} — PLAYER DIED")
                            self._remember_death(pos, a); return False
                        shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                        (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                        sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                        kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                        if kind == 'death':
                            self.log(f"  [explore] poke at {pos} {a} looks like death; abort")
                            self._remember_death(pos, a); return False
                        if kind == 'switch':
                            dp = len(sig_now-cur_sig); dm = len(cur_sig-sig_now)
                            self.log(f"  [explore] poke at {pos} {a} changed world +{dp}/-{dm}")
                            state = SMState.REPLAN
                            changed = True
                            break
                    if changed: break
                    pos = self.pos()
                    pr = perceive(frame, floor_colors=self.floor_colors)  # refresh
                if not changed:
                    self.log("  [explore] exhausted — try GLOBAL_HUNT")
                    state = SMState.GLOBAL_HUNT
                continue

            # FIND_TRIGGER: target locked; hunt for a switch that changes world
            if state == SMState.FIND_TRIGGER:
                self.log(f"  [find-trigger] target locked; hunting switch")
                changed = False
                # === MATH PRIOR ===
                # Rank trigger candidates by Laplacian-energy z-score.
                prior = laplacian_trigger_prior(pr.frame, pr.grid_walkable)
                if prior:
                    top = prior[:8]
                    self.log(f"  [prior] top trigger cells (z-scores): "
                             + ", ".join(f"{c}:{z:+.1f}" for c,z in top[:5]))
                # For each walkable cell, its best-score neighbour trigger
                cell_score: Dict[Tuple[int,int], float] = {}
                cell_trigger: Dict[Tuple[int,int], Tuple[int,int]] = {}
                prior_map = dict(prior)
                for wc in pr.grid_walkable:
                    best_z = -1e9; best_t = None
                    for dr, dc in DELTA4_XY:
                        nb = (wc[0]+dr, wc[1]+dc)
                        if nb in prior_map and prior_map[nb] > best_z:
                            best_z = prior_map[nb]; best_t = nb
                    if best_t is not None:
                        cell_score[wc] = best_z
                        cell_trigger[wc] = best_t
                # Candidates = walkable cells adjacent to a prior-ranked trigger,
                # sorted by z-score desc (fall back to distance for ties)
                cells = [c for c in pr.grid_walkable
                         if any((c, a) not in self.visited_switch_probe for a in DELTA)]
                cells.sort(key=lambda c: (-cell_score.get(c, -1e9),
                                           abs(c[0]-pos[0])+abs(c[1]-pos[1])))
                # Ensure current position is FIRST if it has any unprobed dir
                if pos in cells:
                    cells.remove(pos); cells.insert(0, pos)
                pokes = 0
                cur_pos = pos
                for tcell in cells[:12]:
                    if pokes >= self.cfg.max_explore_pokes or cur_pos is None:
                        break
                    path = bfs_path((pr.grid_walkable | {cur_pos}) - self.pseudo_walls, cur_pos, tcell)
                    self.log(f"    [ft-visit] {cur_pos} -> {tcell} z="
                             f"{cell_score.get(tcell,-99):+.2f} plen="
                             f"{len(path) if path else 'X'}")
                    if path is None:
                        continue
                    died = False
                    for a in path:
                        frame, lvl = self.step(a); steps_total += 1
                        if frame is None: died = True; break
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** SOLVED during trigger-walk ***"); return True
                    if died: return False
                    cur_pos = self.pos()
                    if cur_pos is None:
                        continue
                    # Sort poke directions so the one pointing at the
                    # math-prior winner is tried FIRST.
                    best_trigger = cell_trigger.get(cur_pos)
                    def _dir_score(item):
                        a, (dr, dc) = item
                        nb = (cur_pos[0]+dr, cur_pos[1]+dc)
                        if best_trigger is not None and nb == best_trigger:
                            return -1e6  # highest priority
                        return prior_map.get(nb, 0.0) * -1  # higher z first
                    for a, (dr, dc) in sorted(DELTA.items(), key=_dir_score):
                        nb = (cur_pos[0]+dr, cur_pos[1]+dc)
                        if nb in pr.grid_walkable:
                            continue  # walking, not probing
                        key = (cur_pos, a)
                        if key in self.visited_switch_probe:
                            continue
                        self.visited_switch_probe.add(key)
                        frame, lvl = self.step(a); steps_total += 1
                        pokes += 1
                        if frame is None: return False
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** SOLVED via trigger-poke ***"); return True
                        pr_now = perceive(frame, floor_colors=self.floor_colors)
                        p2 = detect_player_pos(frame)
                        if p2 is None:
                            self.log(f"  [find-trigger] {cur_pos} {a} — DIED; abort")
                            self._remember_death(cur_pos, a); return False
                        shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                        (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                        sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                        kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                        if kind == 'death':
                            self.log(f"  [find-trigger] {cur_pos} {a} death-like; abort")
                            self._remember_death(cur_pos, a); return False
                        if kind == 'switch':
                            dp = len(sig_now-cur_sig); dm = len(cur_sig-sig_now)
                            self.log(f"  [find-trigger] SWITCH at {cur_pos} {a} +{dp}/-{dm}")
                            # Unlock previously-locked targets — they may be open now
                            for lc in list(self.locked_targets):
                                self.locked_targets.discard(lc)
                            # Drop the "enter" tried-flag so we can retry
                            for lc in list(self.visited_switch_probe):
                                if isinstance(lc, tuple) and lc and lc[0] == 'enter':
                                    self.visited_switch_probe.discard(lc)
                            state = SMState.REPLAN
                            changed = True
                            break
                    if changed: break
                    cur_pos = self.pos()
                    pr = perceive(frame, floor_colors=self.floor_colors)
                if not changed:
                    self.log("  [find-trigger] exhausted — mark target dead, REPLAN")
                    if target is not None:
                        self.dead_targets.add(target['cell'])
                        target = None
                    state = SMState.REPLAN
                continue

            # GLOBAL_HUNT: walk to top-z cells anywhere on map and probe them
            if state == SMState.GLOBAL_HUNT:
                self.log("  [global-hunt] visiting top-z cells map-wide")
                prior = laplacian_trigger_prior(pr.frame, pr.grid_walkable)
                # Build a permissive walkable graph: include cells we've never
                # tried, even if not in pr.grid_walkable. Relax pseudo_walls for
                # planning; calibration will re-confirm via bumps.
                planning_walk = (pr.grid_walkable | self.confirmed_walkable
                                  | {pos}) - self.pseudo_walls
                changed = False
                # Limit to top-20 by z-score
                for tcell, z in prior[:20]:
                    if z < 0.3:
                        break
                    # BFS to a walkable cell adjacent to tcell
                    adj = [(tcell[0]+dr, tcell[1]+dc)
                           for dr, dc in DELTA4_XY
                           if (tcell[0]+dr, tcell[1]+dc) in planning_walk]
                    if not adj:
                        continue
                    cur_pos = self.pos()
                    if cur_pos is None: return False
                    best_path = None; best_target = None
                    for adj_cell in adj:
                        path = bfs_path(planning_walk, cur_pos, adj_cell)
                        if path and (best_path is None or len(path) < len(best_path)):
                            best_path = path; best_target = adj_cell
                    if best_path is None:
                        continue
                    self.log(f"    [gh] {tcell} z={z:+.2f} via {best_target} "
                             f"path={len(best_path)} actions={''.join(best_path)}")
                    # Walk the path
                    walk_died = False
                    for a in best_path:
                        before_pos = self.pos()
                        frame, lvl = self.step(a); steps_total += 1
                        if frame is None:
                            self.log("    [gh] frame None during walk — abort")
                            return False
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** LEVEL COMPLETED in global-hunt walk ***")
                            return True
                        if self.pos() is None:
                            self.log(f"    [gh-walk] {a} from {before_pos} — player died")
                            self._remember_death(before_pos, a)
                            walk_died = True
                            break
                    if walk_died:
                        # Don't abort whole hunt — restart loop after env reset
                        # would be ideal, but we only have one life here.
                        return False
                        if lvl > self.cfg.starting_level:
                            self.log(f"*** LEVEL COMPLETED in global-hunt walk ***")
                            return True
                    cur_pos = self.pos()
                    if cur_pos is None: continue
                    # Poke toward tcell
                    dr = (tcell[0] - cur_pos[0]) // 5 if tcell[0] != cur_pos[0] else 0
                    dc = (tcell[1] - cur_pos[1]) // 5 if tcell[1] != cur_pos[1] else 0
                    poke_action = None
                    for a, (xdr, xdc) in DELTA.items():
                        if xdr == dr*5 and xdc == dc*5:
                            poke_action = a; break
                    if poke_action is None: continue
                    key = (cur_pos, poke_action)
                    if key in self.visited_switch_probe: continue
                    self.visited_switch_probe.add(key)
                    frame, lvl = self.step(poke_action); steps_total += 1
                    if frame is None: return False
                    if lvl > self.cfg.starting_level:
                        self.log(f"*** LEVEL COMPLETED via global-hunt poke ***")
                        return True
                    pr_now = perceive(frame, floor_colors=self.floor_colors)
                    p2 = detect_player_pos(frame)
                    if p2 is None:
                        self._remember_death(cur_pos, poke_action); return False
                    shadow_mask2 = {p2,(p2[0]-5,p2[1]),(p2[0]+5,p2[1]),
                                    (p2[0],p2[1]-5),(p2[0],p2[1]+5)}
                    sig_now = walkable_sig(pr_now, exclude=shadow_mask2)
                    kind = self._classify_delta(cur_sig, sig_now, frame, lvl)
                    if kind == 'death':
                        self._remember_death(cur_pos, poke_action); return False
                    if kind == 'switch':
                        dp = len(sig_now-cur_sig); dm = len(cur_sig-sig_now)
                        self.log(f"  [global-hunt] SWITCH at {cur_pos} {poke_action} +{dp}/-{dm}")
                        for lc in list(self.locked_targets):
                            self.locked_targets.discard(lc)
                        for lc in list(self.visited_switch_probe):
                            if isinstance(lc, tuple) and lc and lc[0] == 'enter':
                                self.visited_switch_probe.discard(lc)
                        state = SMState.REPLAN
                        changed = True
                        break
                if not changed:
                    self.log("  [global-hunt] exhausted — STUCK")
                    state = SMState.STUCK
                continue

            if state == SMState.STUCK:
                self.log("[halt] stuck")
                self._save_walkability()
                return False

        self.log("[halt] max outer iterations reached")
        self._save_walkability()
        return False

    def _is_adjacent_walkable(self, cell, walkable):
        return any((cell[0]+dr, cell[1]+dc) in walkable
                   for dr, dc in DELTA.values())
