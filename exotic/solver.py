"""
Orchestrator — wires perception → TDA → probing → group planning →
potential field → action execution into one loop.

High-level control flow per level:

    1. PERCEIVE: extract entities, walkable grid, color histogram.
    2. ANALYZE TOPOLOGY: compute components, loops, articulations.
       If `classify_level == disconnected`, we know we'll need a pusher
       and where to look for it (`bridge_candidates`).
    3. PROBE: actively classify each unknown entity by poking.
       Produces trigger deltas, pusher maps, collectible set, exit cell.
    4. PLAN TRIGGER CROSSINGS: Cayley graph BFS on the product group to
       find the minimum multi-set of trigger crossings that lands in
       the goal coset.
    5. SOLVE POTENTIAL FIELD: set dirichlet sinks at pending triggers
       (weighted by remaining crossings), collectibles, and the exit.
       Gauss-Seidel relaxation gives φ.
    6. EXECUTE: at each step, action = steepest descent on φ. After each
       step, update state (decrement crossing count, remove collected
       cell) and re-solve.
    7. If we die or level progresses, loop.

This design is deliberately stratified — each layer speaks a different
mathematical language (topology, group theory, PDE) but they compose
through clean interfaces. Replacing any single layer (e.g. swapping
Laplace for a learned value network) doesn't require touching the others.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Callable
import numpy as np

from .perception import perceive, PerceptionResult, Entity
from .tda import compute_tda, classify_level, bridge_candidates, TopologicalSignature
from .potential_field import (FieldSpec, PotentialField, solve_laplace,
                               update_after_step)
from .group_state import (GroupState, GroupSpec, plan_group_transitions,
                           crossings_per_trigger, CrossingPlan)
from .dynamics_probe import (ProbeReport, ProbeResult,
                              KIND_TRIGGER, KIND_COLLECTIBLE, KIND_PUSHER,
                              KIND_EXIT, KIND_WALL, KIND_HAZARD,
                              detect_player_pos)


DELTA_ACT = {'U': (-5, 0), 'D': (5, 0), 'L': (0, -5), 'R': (0, 5)}


@dataclass
class SolverTrace:
    actions: List[str] = field(default_factory=list)
    positions: List[Tuple[int, int]] = field(default_factory=list)
    events: List[str] = field(default_factory=list)

    def record(self, action: str, pos: Optional[Tuple[int, int]], note: str = ""):
        self.actions.append(action)
        self.positions.append(pos if pos else (-1, -1))
        if note:
            self.events.append(f"step {len(self.actions)}: {note}")


@dataclass
class SolverConfig:
    player_color: int = 12
    max_steps_per_level: int = 300
    budget_between_refills: int = 20  # ls20 step budget


class ExoticSolver:
    """
    Top-level solver. Callable from a harness that provides:
      - env_step(action) -> StepResult with .frame, .levels_completed
      - initial frame via env.reset() or equivalent
    The solver is stateless re: game-specific constants; everything is
    inferred or configured.
    """

    def __init__(self, env_step: Callable, get_frame: Callable,
                 config: Optional[SolverConfig] = None):
        self.env_step = env_step
        self.get_frame = get_frame
        self.cfg = config or SolverConfig()
        self.trace = SolverTrace()

    # --- Pipeline stages ---

    def percept(self) -> PerceptionResult:
        return perceive(self.get_frame())

    def topology(self, pr: PerceptionResult) -> TopologicalSignature:
        return compute_tda(pr.grid_walkable, pr.walkable_mask)

    def report_from_probes(self, pr: PerceptionResult,
                            probes: Dict[int, ProbeResult]) -> ProbeReport:
        """Aggregate ProbeResults into a ProbeReport."""
        trigger_cells: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
        pusher_map: Dict[Tuple[int, int], Tuple[int, int]] = {}
        walls, colls = [], []
        exit_cell = None
        for eid, r in probes.items():
            ent = next((e for e in pr.entities if e.eid == eid), None)
            if ent is None:
                continue
            cell = sorted(ent.grid_cells)[0] if ent.grid_cells else None
            if r.kind == KIND_TRIGGER and cell is not None:
                # Default delta: (+1, 0, 0) rotation; probing refines later
                trigger_cells[cell] = (1, 0, 0)
            elif r.kind == KIND_PUSHER and r.pusher_src and r.pusher_dst:
                pusher_map[r.pusher_src] = r.pusher_dst
            elif r.kind == KIND_COLLECTIBLE:
                colls.append(eid)
            elif r.kind == KIND_WALL:
                walls.append(eid)
            elif r.kind == KIND_EXIT and cell is not None:
                exit_cell = cell
        return ProbeReport(
            results=probes,
            trigger_cells=trigger_cells,
            pusher_map=pusher_map,
            walls=walls,
            collectibles=colls,
            exit_cell=exit_cell,
        )

    def plan_modifiers(self, report: ProbeReport,
                        current_state: GroupState,
                        goal_predicate: Callable[[GroupState], bool]
                        ) -> Optional[CrossingPlan]:
        spec = GroupSpec(
            triggers=report.trigger_cells,
            collectibles=frozenset(
                # map collectible entity ids back to cells via perception,
                # caller must supply; for now empty set
            ),
            goal_predicate=goal_predicate,
        )
        return plan_group_transitions(current_state, spec)

    def build_field(self, pr: PerceptionResult, report: ProbeReport,
                     crossings: Dict[Tuple[int, int], int]) -> PotentialField:
        colls = {}
        for eid in report.collectibles:
            ent = next((e for e in pr.entities if e.eid == eid), None)
            if ent and ent.grid_cells:
                colls[sorted(ent.grid_cells)[0]] = 1.0
        spec = FieldSpec(
            walkable=pr.grid_walkable,
            exit_cell=report.exit_cell,
            triggers_remaining=dict(crossings),
            collectibles_remaining=colls,
        )
        return solve_laplace(spec)

    # --- Execution loop ---

    def step_along_field(self, pf: PotentialField,
                          pos: Tuple[int, int]) -> Tuple[Optional[str], Optional[Tuple[int,int]]]:
        action = pf.action_at(pos)
        if action is None:
            return None, None
        r = self.env_step(action)
        frame = getattr(r, 'frame', None)
        if isinstance(frame, list) and frame:
            frame = frame[0]
        new_pos = detect_player_pos(frame, self.cfg.player_color) if frame is not None else None
        return action, new_pos

    def play_level(self, goal_predicate: Callable[[GroupState], bool],
                    initial_state: Optional[GroupState] = None
                    ) -> bool:
        """Run one full level. Returns True if level completed."""
        state = initial_state or GroupState()
        for outer in range(8):  # bounded re-plan cycles
            pr = self.percept()
            sig = self.topology(pr)
            level_arch = classify_level(sig)
            self.trace.events.append(f"outer={outer} arch={level_arch} {sig.summary()}")

            # For now, stub: no live probing in this skeleton — the solver
            # assumes a ProbeReport was prepared externally or cached.
            # Full implementation plugs in probe_entity() from dynamics_probe.
            report = ProbeReport(results={}, trigger_cells={},
                                 pusher_map={}, walls=[], collectibles=[],
                                 exit_cell=None)

            crossings: Dict[Tuple[int, int], int] = {}
            plan = self.plan_modifiers(report, state, goal_predicate)
            if plan is not None:
                crossings = crossings_per_trigger(plan)

            pf = self.build_field(pr, report, crossings)

            pos = detect_player_pos(self.get_frame(), self.cfg.player_color)
            if pos is None:
                self.trace.events.append("lost player — aborting")
                return False

            for step in range(self.cfg.max_steps_per_level):
                action, new_pos = self.step_along_field(pf, pos)
                if action is None:
                    self.trace.events.append("no descent direction")
                    break
                self.trace.record(action, new_pos)
                if new_pos is None:
                    self.trace.events.append("frame lost (death?)")
                    return False
                # Trigger crossing detection
                if new_pos in crossings and crossings[new_pos] > 0:
                    crossings[new_pos] -= 1
                    pf = update_after_step(pf, new_pos)
                elif new_pos in pf.spec.collectibles_remaining:
                    pf = update_after_step(pf, new_pos)
                pos = new_pos
                # Goal check via potential: reaching exit cell with pending=0
                if report.exit_cell and new_pos == report.exit_cell \
                        and all(v <= 0 for v in crossings.values()):
                    self.trace.events.append("reached exit")
                    return True
        return False


# --- Convenience API ---

def solve_game(env_step: Callable, get_frame: Callable,
                goal_predicates: List[Callable[[GroupState], bool]],
                config: Optional[SolverConfig] = None) -> List[bool]:
    """Run the solver across a list of levels. Returns success per level."""
    solver = ExoticSolver(env_step, get_frame, config)
    results = []
    for gp in goal_predicates:
        results.append(solver.play_level(gp))
    return results
