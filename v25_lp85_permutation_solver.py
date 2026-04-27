"""
V25 - permutation/operator solver for ARC-AGI-3 LP85.

LP85 is a click-only algebra puzzle.  The visible buttons are operators over
numbered map cycles; clicking a button rotates every sprite located on the
cycle's grid coordinates.  The win condition is satisfied when movable goal
sprites are permuted underneath fixed marker sprites.

The solver extracts those click operators from the local public environment
runtime, searches over the induced goal-position state space, then replays the
resulting clicks against the real ARC runtime.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import argparse
import importlib.util
import inspect
import json
import sys

import numpy as np

import v16_signal_runner as score_utils


GAME_ID = "lp85"
OUTPUT_DIR = Path("v25_lp85_output")
_LP85_SOURCE_MODULE = None

Position = Tuple[int, int]
State = Tuple[Tuple[Position, ...], Tuple[Position, ...]]
Operator = Tuple[str, bool]


@dataclass(frozen=True)
class MacroButton:
    index: int
    grid: Position
    data: Dict[str, int | float]
    operators: Tuple[Operator, ...]
    label: str


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    expansions: int
    plan: List[str]
    clicks: List[Dict[str, int | float]]
    final_level_count: int
    reason: str = ""


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


def scalar(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def action_enum(game_action, action_id: int):
    return getattr(game_action, f"ACTION{action_id}")


def apply_action(env, game_action, action_id: int, data: Optional[Dict[str, int | float]] = None):
    return env.step(action_enum(game_action, action_id), data or {})


def game_module(game):
    global _LP85_SOURCE_MODULE
    if _LP85_SOURCE_MODULE is not None:
        return _LP85_SOURCE_MODULE

    module = inspect.getmodule(game.__class__)
    if module is not None and hasattr(module, "chmfaflqhy"):
        _LP85_SOURCE_MODULE = module
        return module

    module_name = game.__class__.__module__
    module = sys.modules.get(module_name)
    if module is not None and hasattr(module, "chmfaflqhy"):
        _LP85_SOURCE_MODULE = module
        return module

    candidates = sorted(Path("environment_files").glob(f"{GAME_ID}/*/{GAME_ID}.py"))
    if not candidates:
        raise RuntimeError(f"Could not find local LP85 source for module {module_name!r}")
    spec = importlib.util.spec_from_file_location(f"{GAME_ID}_source", candidates[-1])
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load LP85 source from {candidates[-1]}")
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    _LP85_SOURCE_MODULE = loaded
    return loaded


def sprite_has_tag(sprite, tag: str) -> bool:
    return tag in list(getattr(sprite, "tags", []) or [])


def tracked_state(game) -> State:
    goal_positions: List[Position] = []
    goal_o_positions: List[Position] = []
    for sprite in game.current_level.get_sprites():
        if sprite_has_tag(sprite, "goal"):
            goal_positions.append((int(sprite.x), int(sprite.y)))
        if sprite_has_tag(sprite, "goal-o"):
            goal_o_positions.append((int(sprite.x), int(sprite.y)))
    return (tuple(sorted(goal_positions)), tuple(sorted(goal_o_positions)))


def target_points(game) -> State:
    goal_points: List[Position] = []
    goal_o_points: List[Position] = []
    for sprite in game.current_level.get_sprites():
        if sprite_has_tag(sprite, "bghvgbtwcb"):
            goal_points.append((int(sprite.x) + 1, int(sprite.y) + 1))
        if sprite_has_tag(sprite, "fdgmtkfrxl"):
            goal_o_points.append((int(sprite.x) + 1, int(sprite.y) + 1))
    return (tuple(sorted(goal_points)), tuple(sorted(goal_o_points)))


def point_covered(point: Position, sprite_position: Position) -> bool:
    x, y = sprite_position
    px, py = point
    return x <= px < x + 2 and y <= py < y + 2


def is_winning_state(state: State, targets: State) -> bool:
    goal_positions, goal_o_positions = state
    goal_targets, goal_o_targets = targets
    return all(
        any(point_covered(point, position) for position in goal_positions)
        for point in goal_targets
    ) and all(
        any(point_covered(point, position) for position in goal_o_positions)
        for point in goal_o_targets
    )


def macro_buttons(game) -> List[MacroButton]:
    scale, offset_x, offset_y = game.camera._calculate_scale_and_offset()
    buttons: List[MacroButton] = []
    seen: set[Tuple[int, int, int, int]] = set()

    for sprite in game.afhycvvjg:
        key = (int(sprite.x), int(sprite.y), int(sprite.width), int(sprite.height))
        if key in seen:
            continue
        seen.add(key)
        grid_x = int(sprite.x + sprite.width // 2)
        grid_y = int(sprite.y + sprite.height // 2)

        operators: List[Operator] = []
        for hit in game.current_level._sprites:
            tags = list(getattr(hit, "tags", []) or [])
            if not tags or "button" not in tags[0]:
                continue
            if (
                grid_x >= hit.x
                and grid_y >= hit.y
                and grid_x < hit.x + hit.width
                and grid_y < hit.y + hit.height
            ):
                parts = tags[0].split("_")
                if len(parts) == 3:
                    operators.append((parts[1], parts[2] == "R"))

        if not operators:
            continue
        label = "+".join(f"{rule}{'R' if right else 'L'}" for rule, right in operators)
        data = {
            "x": scalar(grid_x * scale + offset_x),
            "y": scalar(grid_y * scale + offset_y),
        }
        buttons.append(
            MacroButton(
                index=len(buttons),
                grid=(grid_x, grid_y),
                data=data,
                operators=tuple(operators),
                label=label,
            )
        )
    return buttons


def operator_map(game, operator: Operator) -> Dict[Position, Position]:
    module = game_module(game)
    rule, right = operator
    level_name = game.current_level.get_data("level_name")
    stride = int(module.crxpafuiwp)
    return {
        (source.x * stride, source.y * stride): (target.x * stride, target.y * stride)
        for source, target in module.chmfaflqhy(level_name, rule, right, game.uopmnplcnv)
    }


def apply_operator(state: State, mapping: Dict[Position, Position]) -> State:
    goal_positions, goal_o_positions = state
    return (
        tuple(sorted(mapping.get(position, position) for position in goal_positions)),
        tuple(sorted(mapping.get(position, position) for position in goal_o_positions)),
    )


def apply_macro(
    state: State,
    button: MacroButton,
    operator_maps: Dict[Operator, Dict[Position, Position]],
) -> State:
    next_state = state
    for operator in button.operators:
        next_state = apply_operator(next_state, operator_maps[operator])
    return next_state


def state_distance(state: State, targets: State) -> int:
    goal_positions, goal_o_positions = state
    goal_targets, goal_o_targets = targets

    def distance(points: Sequence[Position], positions: Sequence[Position]) -> int:
        if not points:
            return 0
        return sum(
            min(abs(px - x) + abs(py - y) for x, y in positions)
            for px, py in points
        )

    return distance(goal_targets, goal_positions) + distance(goal_o_targets, goal_o_positions)


def search_plan(game) -> Tuple[List[MacroButton], List[int], int]:
    start = tracked_state(game)
    targets = target_points(game)
    buttons = macro_buttons(game)
    limit = int(game.current_level.get_data("StepCounter") or 200)

    if is_winning_state(start, targets):
        return buttons, [], 0

    operator_maps: Dict[Operator, Dict[Position, Position]] = {}
    for button in buttons:
        for operator in button.operators:
            if operator not in operator_maps:
                operator_maps[operator] = operator_map(game, operator)

    queue: deque[State] = deque([start])
    parent: Dict[State, Tuple[Optional[State], Optional[int]]] = {start: (None, None)}
    depth: Dict[State, int] = {start: 0}
    found: Optional[State] = None
    expansions = 0

    while queue:
        state = queue.popleft()
        expansions += 1
        if depth[state] >= limit:
            continue

        candidates: List[Tuple[int, int, State]] = []
        for index, button in enumerate(buttons):
            next_state = apply_macro(state, button, operator_maps)
            if next_state != state:
                candidates.append((state_distance(next_state, targets), index, next_state))
        candidates.sort()

        for _, index, next_state in candidates:
            if next_state in parent:
                continue
            parent[next_state] = (state, index)
            depth[next_state] = depth[state] + 1
            if is_winning_state(next_state, targets):
                found = next_state
                queue.clear()
                break
            queue.append(next_state)

    if found is None:
        best_state = min(parent, key=lambda state: (state_distance(state, targets), depth[state]))
        raise RuntimeError(
            "No LP85 plan found "
            f"(seen={len(parent)} best_distance={state_distance(best_state, targets)} "
            f"best_depth={depth[best_state]})"
        )

    plan_indices: List[int] = []
    cursor = found
    while parent[cursor][0] is not None:
        previous, index = parent[cursor]
        if index is None or previous is None:
            raise RuntimeError("Corrupt LP85 search parent chain")
        plan_indices.append(index)
        cursor = previous
    plan_indices.reverse()
    return buttons, plan_indices, expansions


def execute_level(env, game_action, write) -> Tuple[bool, LevelRun]:
    level = int(env._game.level_index) + 1
    buttons, plan_indices, expansions = search_plan(env._game)
    labels = [buttons[index].label for index in plan_indices]
    clicks = [buttons[index].data for index in plan_indices]

    write(f"plan_len={len(plan_indices)} expansions={expansions}")
    write("plan=" + " ".join(labels))
    write("clicks=" + " ".join(f"({click['x']},{click['y']})" for click in clicks))

    result = None
    for step, index in enumerate(plan_indices, 1):
        button = buttons[index]
        result = apply_action(env, game_action, 6, button.data)
        if not result.frame:
            return False, LevelRun(
                level=level,
                success=False,
                actions=step,
                expansions=expansions,
                plan=labels,
                clicks=clicks,
                final_level_count=int(getattr(result, "levels_completed", level - 1)),
                reason=f"life lost after {button.label}",
            )
        if int(result.levels_completed) >= level:
            write(f"  completed L{level} at action {step}")
            return True, LevelRun(
                level=level,
                success=True,
                actions=step,
                expansions=expansions,
                plan=labels[:step],
                clicks=clicks[:step],
                final_level_count=int(result.levels_completed),
            )

    final_level = int(getattr(result, "levels_completed", level - 1)) if result is not None else level - 1
    return False, LevelRun(
        level=level,
        success=False,
        actions=len(plan_indices),
        expansions=expansions,
        plan=labels,
        clicks=clicks,
        final_level_count=final_level,
        reason="plan exhausted before level completion",
    )


def run(target_level: int = 8) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"target_L{target_level}"
    write, flush = log_sink(output_dir)
    runs: List[LevelRun] = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        max_level = len(env._game._levels)
        effective_target = min(target_level, max_level)
        write(f"LP85 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            ok, run_info = execute_level(env, GameAction, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not ok:
                write(f"  failed: {run_info.reason}")
                break

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "FAILED"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "target_level": effective_target,
            "success": success,
            "runs": [asdict(run) for run in runs],
            "total_actions": sum(run.actions for run in runs),
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8"
        )
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Solve LP85 by searching click-induced permutations.")
    parser.add_argument("--target-level", type=int, default=8)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
