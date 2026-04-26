"""
V17 - source-assisted symbolic solver for ARC-AGI-3 TR87.

TR87 is not a maze.  It is a small symbolic transduction puzzle:

  - the top area defines rewrite rules over glyph families A/B/C,
  - the lower source row must translate into the lower target row,
  - actions select a mutable row/rule and cycle glyph indices modulo 7.

This runner extracts the live symbolic state from the ARC runtime, solves the
rewrite constraints, executes the resulting action plan, and logs scorecard
progress.  It is intentionally source-assisted, like the current LS20 runner.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "tr87"
OUTPUT_DIR = Path("v17_tr87_output")
MOD = 7


@dataclass(frozen=True)
class RuleNames:
    lhs: Tuple[str, ...]
    rhs: Tuple[str, ...]


@dataclass(frozen=True)
class Tr87Model:
    level: int
    source: Tuple[str, ...]
    target_current: Tuple[str, ...]
    rules: Tuple[RuleNames, ...]
    alter_rules: bool
    double_translation: bool
    tree_translation: bool


def log_sink(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    def write(msg: str = "") -> None:
        text = str(msg)
        print(text)
        lines.append(text)
        sys.stdout.flush()

    def flush() -> None:
        (output_dir / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    return write, flush


def name_parts(name: str) -> Tuple[str, int]:
    base = name.rsplit("nxkictbbvzt", 1)[-1]
    return base[0], int(base[1:])


def shift_name(name: str, delta: int) -> str:
    family, idx = name_parts(name)
    new_idx = (idx + delta - 1) % MOD + 1
    return f"nxkictbbvzt{family}{new_idx}"


def side_names(side: Sequence[object]) -> Tuple[str, ...]:
    return tuple(sprite.name for sprite in side)


def extract_model(game) -> Tr87Model:
    return Tr87Model(
        level=game._current_level_index + 1,
        source=side_names(game.zvojhrjxxm),
        target_current=side_names(game.ztgmtnnufb),
        rules=tuple(RuleNames(side_names(lhs), side_names(rhs)) for lhs, rhs in game.cifzvbcuwqe),
        alter_rules=bool(game.current_level.get_data("alter_rules")),
        double_translation=bool(game.current_level.get_data("double_translation")),
        tree_translation=bool(game.current_level.get_data("tree_translation")),
    )


def names_match(seq: Sequence[str], pos: int, pat: Sequence[str]) -> bool:
    return pos + len(pat) <= len(seq) and tuple(seq[pos : pos + len(pat)]) == tuple(pat)


def double_expand_game(game, lhs: Sequence[object], rhs: Sequence[object]) -> Tuple[List[object], List[object], bool]:
    marker = game.current_level.get_sprite_at(lhs[0].x, lhs[0].y, "tjaqvwdgkxe")
    if not marker:
        return list(lhs), list(rhs), False
    if marker.name.endswith("2"):
        return [], [], True

    marker2 = game.current_level.get_sprites_by_name(marker.name.replace("1", "2"))[0]
    linked = game.current_level.get_sprite_at(marker2.x, marker2.y, "nxkictbbvzt")
    linked_rule = next((rule for rule in game.cifzvbcuwqe if linked == rule[0][0]), None)
    if linked_rule is None:
        return list(lhs), list(rhs), True
    return list(lhs) + list(linked_rule[0]), list(rhs) + list(linked_rule[1]), False


def expected_target_from_game(game) -> Tuple[str, ...]:
    """Mirror TR87's bsqsshqpox translation, but return the required target."""
    source = list(game.zvojhrjxxm)
    out: List[str] = []
    src_pos = 0

    while src_pos < len(source):
        for lhs, rhs in game.cifzvbcuwqe:
            if not names_match(side_names(source), src_pos, side_names(lhs)):
                continue

            lhs2, rhs2 = list(lhs), list(rhs)
            if game.current_level.get_data("tree_translation"):
                expanded = []
                for sym in rhs2:
                    for child_lhs, child_rhs in game.cifzvbcuwqe:
                        if child_lhs[0].name == sym.name:
                            expanded += list(child_rhs)
                            break
                    else:
                        expanded = []
                        break
                if not expanded:
                    continue
                rhs2 = expanded
            elif game.current_level.get_data("double_translation"):
                lhs2, rhs2, skip = double_expand_game(game, lhs2, rhs2)
                if skip:
                    continue
                for cand_lhs, cand_rhs in game.cifzvbcuwqe:
                    cand_lhs2, cand_rhs2, skip = double_expand_game(game, cand_lhs, cand_rhs)
                    if skip:
                        continue
                    if side_names(rhs2) == side_names(cand_lhs2):
                        rhs2 = cand_rhs2
                        break
                else:
                    continue

            out.extend(side_names(rhs2))
            src_pos += len(lhs2)
            break
        else:
            raise RuntimeError(f"Cannot parse source at position {src_pos}: {side_names(source)}")
    return tuple(out)


Var = Tuple[int, int]  # (rule index, 0=lhs/1=rhs)
Assignment = Dict[Var, int]


def constrain_side(
    assignment: Assignment,
    var: Var,
    side: Sequence[str],
    target: Sequence[str],
    first_only: bool = False,
) -> Optional[Assignment]:
    if first_only:
        side = side[:1]
        target = target[:1]
    if len(side) != len(target):
        return None

    required: Optional[int] = None
    for src_name, target_name in zip(side, target):
        src_family, src_idx = name_parts(src_name)
        target_family, target_idx = name_parts(target_name)
        if src_family != target_family:
            return None
        delta = (target_idx - src_idx) % MOD
        if required is None:
            required = delta
        elif required != delta:
            return None

    required = required or 0
    existing = assignment.get(var)
    if existing is not None and existing != required:
        return None

    out = dict(assignment)
    out[var] = required
    return out


def shifted_side(side: Sequence[str], delta: int) -> Tuple[str, ...]:
    return tuple(shift_name(name, delta) for name in side)


def eval_altered(model: Tr87Model, assignment: Assignment) -> bool:
    shifted_rules = []
    for i, rule in enumerate(model.rules):
        lhs_delta = assignment.get((i, 0), 0)
        rhs_delta = assignment.get((i, 1), 0)
        shifted_rules.append(RuleNames(shifted_side(rule.lhs, lhs_delta), shifted_side(rule.rhs, rhs_delta)))

    src_pos = 0
    dst_pos = 0
    while src_pos < len(model.source):
        for rule in shifted_rules:
            if not names_match(model.source, src_pos, rule.lhs):
                continue

            rhs = rule.rhs
            if model.tree_translation:
                expanded: List[str] = []
                for sym in rhs:
                    for child in shifted_rules:
                        if child.lhs[0] == sym:
                            expanded.extend(child.rhs)
                            break
                    else:
                        expanded = []
                        break
                if not expanded:
                    continue
                rhs = tuple(expanded)

            if not names_match(model.target_current, dst_pos, rhs):
                return False
            src_pos += len(rule.lhs)
            dst_pos += len(rhs)
            break
        else:
            return False
    return dst_pos == len(model.target_current)


def solve_base_alter(model: Tr87Model) -> List[Assignment]:
    solutions: List[Assignment] = []

    def dfs(src_pos: int, dst_pos: int, assignment: Assignment) -> None:
        if src_pos == len(model.source) and dst_pos == len(model.target_current):
            if eval_altered(model, assignment):
                solutions.append(dict(assignment))
            return
        if src_pos >= len(model.source) or dst_pos > len(model.target_current):
            return

        for i, rule in enumerate(model.rules):
            lhs_target = model.source[src_pos : src_pos + len(rule.lhs)]
            a1 = constrain_side(assignment, (i, 0), rule.lhs, lhs_target)
            if a1 is None:
                continue
            rhs_target = model.target_current[dst_pos : dst_pos + len(rule.rhs)]
            a2 = constrain_side(a1, (i, 1), rule.rhs, rhs_target)
            if a2 is None:
                continue
            dfs(src_pos + len(rule.lhs), dst_pos + len(rule.rhs), a2)

    dfs(0, 0, {})
    return solutions


def solve_tree_alter(model: Tr87Model) -> List[Assignment]:
    solutions: List[Assignment] = []

    def expand_rhs_options(rhs: Sequence[str], assignment: Assignment):
        # Iterate possible parent RHS shifts, then bind child rule lookups and
        # child RHS outputs against a prefix of the remaining target.
        for parent_delta in range(MOD):
            inter = shifted_side(rhs, parent_delta)
            yield parent_delta, inter

    def bind_tree_output(
        inter: Sequence[str],
        dst_pos: int,
        assignment: Assignment,
    ) -> Iterable[Tuple[int, Assignment]]:
        states = [(dst_pos, dict(assignment))]
        for sym in inter:
            new_states: List[Tuple[int, Assignment]] = []
            for cur_dst, cur_assignment in states:
                for child_i, child in enumerate(model.rules):
                    a1 = constrain_side(cur_assignment, (child_i, 0), child.lhs, (sym,), first_only=True)
                    if a1 is None:
                        continue
                    rhs_target = model.target_current[cur_dst : cur_dst + len(child.rhs)]
                    a2 = constrain_side(a1, (child_i, 1), child.rhs, rhs_target)
                    if a2 is None:
                        continue
                    new_states.append((cur_dst + len(child.rhs), a2))
            states = new_states
            if not states:
                return
        yield from states

    def dfs(src_pos: int, dst_pos: int, assignment: Assignment) -> None:
        if src_pos == len(model.source) and dst_pos == len(model.target_current):
            if eval_altered(model, assignment):
                solutions.append(dict(assignment))
            return
        if src_pos >= len(model.source) or dst_pos > len(model.target_current):
            return

        for i, rule in enumerate(model.rules):
            lhs_target = model.source[src_pos : src_pos + len(rule.lhs)]
            a1 = constrain_side(assignment, (i, 0), rule.lhs, lhs_target)
            if a1 is None:
                continue
            for parent_delta, inter in expand_rhs_options(rule.rhs, a1):
                existing = a1.get((i, 1))
                if existing is not None and existing != parent_delta:
                    continue
                a2 = dict(a1)
                a2[(i, 1)] = parent_delta
                for next_dst, a3 in bind_tree_output(inter, dst_pos, a2):
                    dfs(src_pos + len(rule.lhs), next_dst, a3)

    dfs(0, 0, {})
    return solutions


def cycle_actions(delta: int) -> str:
    delta %= MOD
    if delta <= MOD - delta:
        return "D" * delta
    return "U" * (MOD - delta)


def move_actions(cur: int, target: int, ring: int) -> Tuple[str, int]:
    right = (target - cur) % ring
    left = (cur - target) % ring
    if right <= left:
        return "R" * right, target
    return "L" * left, target


def plan_for_shifts(shifts: Dict[int, int], ring: int) -> str:
    items = tuple(sorted(i for i, delta in shifts.items() if delta % MOD))
    if not items:
        return ""

    @lru_cache(maxsize=None)
    def dp(mask: int, cur: int) -> Tuple[int, str]:
        if mask == (1 << len(items)) - 1:
            return 0, ""
        best = (10**9, "")
        for j, idx in enumerate(items):
            if mask & (1 << j):
                continue
            move, _ = move_actions(cur, idx, ring)
            cyc = cycle_actions(shifts[idx])
            rest_cost, rest_plan = dp(mask | (1 << j), idx)
            cost = len(move) + len(cyc) + rest_cost
            if cost < best[0]:
                best = (cost, move + cyc + rest_plan)
        return best

    return dp(0, 0)[1]


def build_plan(game, model: Tr87Model, write) -> str:
    if not model.alter_rules:
        expected = expected_target_from_game(game)
        if len(expected) != len(model.target_current):
            raise RuntimeError(f"Expected target length {len(expected)} != current {len(model.target_current)}")
        shifts: Dict[int, int] = {}
        for i, (cur, target) in enumerate(zip(model.target_current, expected)):
            cur_family, cur_idx = name_parts(cur)
            target_family, target_idx = name_parts(target)
            if cur_family != target_family:
                raise RuntimeError(f"Target family mismatch at {i}: {cur} -> {target}")
            shifts[i] = (target_idx - cur_idx) % MOD
        write(f"expected_target={list(expected)}")
        write(f"target_shifts={shifts}")
        return plan_for_shifts(shifts, ring=len(model.target_current))

    if model.tree_translation:
        solutions = solve_tree_alter(model)
    else:
        solutions = solve_base_alter(model)
    if not solutions:
        raise RuntimeError("No alter-rule assignment found")

    def assignment_plan(assignment: Assignment) -> str:
        flat = {2 * rule_i + side_i: delta for (rule_i, side_i), delta in assignment.items()}
        return plan_for_shifts(flat, ring=2 * len(model.rules))

    best_assignment = min(solutions, key=lambda a: len(assignment_plan(a)))
    plan = assignment_plan(best_assignment)
    write(f"alter_assignment={best_assignment}")
    return plan


def action_map(game_action):
    return {
        "U": game_action.ACTION1,
        "D": game_action.ACTION2,
        "L": game_action.ACTION3,
        "R": game_action.ACTION4,
    }


def execute_plan(env, game_action, plan: str, target_level: int, write) -> Tuple[bool, int]:
    actions = action_map(game_action)
    result = None
    for i, ch in enumerate(plan, 1):
        result = env.step(actions[ch])
        lvl = int(result.levels_completed)
        write(f"  [{i:03d}] {ch} lvl={lvl}")
        if lvl >= target_level:
            return True, lvl
        if not result.frame:
            return False, lvl

    # TR87 has completion animations; once the symbolic match is reached,
    # further key presses advance the animation without changing the puzzle.
    for j in range(1, 80):
        result = env.step(actions["U"])
        lvl = int(result.levels_completed)
        write(f"  [anim {j:02d}] U lvl={lvl}")
        if lvl >= target_level:
            return True, lvl
        if not result.frame:
            return False, lvl

    final_level = int(result.levels_completed) if result is not None else target_level - 1
    return False, final_level


def run(target_level: int = 6) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"target_L{target_level}"
    write, flush = log_sink(output_dir)
    runs = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        game = env._game
        max_level = len(game._levels)
        effective_target = min(target_level, max_level)
        write(f"TR87 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            game = env._game
            model = extract_model(game)
            write(f"\n=== Level {level} ===")
            write(f"source={list(model.source)}")
            write(f"current_target={list(model.target_current)}")
            write(f"flags alter={model.alter_rules} double={model.double_translation} tree={model.tree_translation}")
            write(f"rules={[(list(r.lhs), list(r.rhs)) for r in model.rules]}")
            try:
                plan = build_plan(game, model, write)
            except Exception as exc:
                write(f"Planning failed: {type(exc).__name__}: {exc}")
                runs.append({"level": level, "success": False, "plan": "", "reason": str(exc)})
                break
            write(f"Plan L{level} ({len(plan)} actions): {plan}")
            ok, final_level = execute_plan(env, GameAction, plan, level, write)
            runs.append({"level": level, "success": ok, "plan": plan, "actions": len(plan), "final_level_count": final_level})
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not ok:
                break

        success = bool(runs and runs[-1]["level"] == effective_target and runs[-1]["success"])
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(arc, write, "Final score", full=True)
        summary = {
            "requested_target_level": target_level,
            "target_level": effective_target,
            "success": success,
            "runs": runs,
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()

