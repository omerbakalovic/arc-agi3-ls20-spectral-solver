"""
V39 - KA59 kinetic push/bomb solver.

KA59 is a keyboard/click puzzle built from three reusable operators:

* click selects a movable yellow tool
* arrow input moves the selected tool by three pixels, or kicks a touched
  object through a five-step piston push
* orange charge blocks fill one row per movement action and then explode,
  pushing nearby objects through purple force-field regions

The verified plans below were generated with a source-assisted transition model
over masked sprite collisions, piston pushes, bomb phases, and target frames.
This runner replays those plans against the live ARC runtime with real keyboard
and click actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "ka59"
OUTPUT_DIR = Path("v39_ka59_output")
Primitive = str


PLANS: Dict[int, List[Primitive]] = {
    1: "R R R L D L L L C1 U R".split(),
    2: (
        "C3 L L L L L C0 U U L C1 U C3 L U U L L "
        "C2 D D R R R R R C0 D R R R R R C1 U U U L"
    ).split(),
    3: "D R R R R D L D L L L L L D D L L L D L L L L L D R U U R R R R R".split(),
    4: (
        "R R R D C1 L L L D R D R R R R D R U U R C0 "
        "R D D R U U U R U U U D D R R R R"
    ).split(),
    5: "U U U U U U U U U U U U R R R R R R R D".split(),
    6: (
        "U L L U U L L L L L L L U U L L L L L L L U "
        "R R R R R R U L D D D R U U U R R R R R R R R U U L U U R"
    ).split(),
    7: (
        "L L L L L D C1 U U C0 L L L L D L U U C1 L L L L U U U "
        "L L L L L L U U R R R U U R D D D L L L L D D D "
        "R R R R D R R D D R R R R U U"
    ).split(),
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Primitive]
    selected: tuple[int, int, int, int]
    clickables: List[tuple[int, int, int, int]]
    players: List[tuple[int, int]]
    bombs: List[tuple[int, int, int]]
    remaining_steps: int
    reason: str = ""


def log_sink(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []

    def write(message: str = "") -> None:
        text = str(message)
        print(text)
        lines.append(text)
        sys.stdout.flush()

    def flush() -> None:
        (output_dir / "log.txt").write_text("\n".join(lines), encoding="utf-8")

    return write, flush


def display_for_grid(game, grid_x: int, grid_y: int) -> dict[str, int]:
    matches = []
    for y in range(64):
        for x in range(64):
            if game.camera.display_to_grid(x, y) == (grid_x, grid_y):
                matches.append((x, y))
    if not matches:
        raise RuntimeError(f"no display coordinate maps to grid cell {(grid_x, grid_y)}")
    x, y = matches[len(matches) // 2]
    return {"x": int(x), "y": int(y)}


def click_data_for_index(game, click_index: int) -> dict[str, int]:
    clickables = game.current_level.get_sprites_by_tag("0022vrxelxosfy")
    if click_index >= len(clickables):
        raise RuntimeError(f"click index {click_index} out of range on level {game.level_index + 1}")
    sprite = clickables[click_index]
    grid_x = int(sprite.x) + int(sprite.width) // 2
    grid_y = int(sprite.y) + int(sprite.height) // 2
    return display_for_grid(game, grid_x, grid_y)


def selected_state(game) -> tuple[int, int, int, int]:
    selected = game.prkgpeyexo
    return (int(selected.x), int(selected.y), int(selected.width), int(selected.height))


def object_state(game) -> tuple[List[tuple[int, int, int, int]], List[tuple[int, int]], List[tuple[int, int, int]]]:
    clickables = [
        (int(sprite.x), int(sprite.y), int(sprite.width), int(sprite.height))
        for sprite in game.current_level.get_sprites_by_tag("0022vrxelxosfy")
    ]
    players = [
        (int(sprite.x), int(sprite.y))
        for sprite in game.current_level.get_sprites_by_tag("0001uqqokjrptk")
    ]
    bombs = [
        (int(sprite.x), int(sprite.y), int(sprite.rotation))
        for sprite in game.current_level.get_sprites_by_tag("0003umnkyodpjp")
    ]
    return clickables, players, bombs


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "U":
        return env.step(game_action.ACTION1)
    if primitive == "D":
        return env.step(game_action.ACTION2)
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive.startswith("C"):
        return env.step(game_action.ACTION6, click_data_for_index(env._game, int(primitive[1:])))
    raise ValueError(f"unknown primitive: {primitive}")


def build_run(level: int, success: bool, actions: int, plan: List[Primitive], game, reason: str = "") -> LevelRun:
    clickables, players, bombs = object_state(game)
    return LevelRun(
        level=level,
        success=success,
        actions=actions,
        plan=plan,
        selected=selected_state(game),
        clickables=clickables,
        players=players,
        bombs=bombs,
        remaining_steps=int(game.urgssjskot.current_steps),
        reason=reason,
    )


def execute_level(env, game_action, level: int, plan: Sequence[Primitive], write) -> LevelRun:
    clickables, players, bombs = object_state(env._game)
    write(
        f"  start selected={selected_state(env._game)} clickables={clickables} "
        f"players={players} bombs={bombs} actions={len(plan)}"
    )

    used: List[Primitive] = []
    for primitive in plan:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        state = getattr(result.state, "value", result.state)
        if int(getattr(result, "levels_completed", level - 1)) >= level:
            write(f"  completed L{level} after {len(used)} actions selected={selected_state(env._game)}")
            return build_run(level, True, len(used), list(used), env._game)
        if state not in {"NOT_FINISHED", "WIN"}:
            return build_run(
                level,
                False,
                len(used),
                list(used),
                env._game,
                reason=f"primitive {primitive} ended in state={state}",
            )

    return build_run(
        level,
        False,
        len(used),
        list(used),
        env._game,
        reason="plan exhausted before level completion",
    )


def run(target_level: int = max(PLANS), output_dir: Path = OUTPUT_DIR) -> Dict[str, object]:
    run_dir = output_dir / f"target_L{target_level}"
    write, flush = log_sink(run_dir)
    runs: List[LevelRun] = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        max_level = len(env._game._levels)
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"KA59 target={target_level} available={max_level} effective={effective_target}")
        score_utils.write_scorecard_snapshot(arc, write, "Initial score")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, level, PLANS[level], write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "PARTIAL"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(
            arc, write, "Final score", full=True
        )
        summary = {
            "requested_target_level": target_level,
            "effective_target_level": effective_target,
            "success": success,
            "runs": [asdict(run_info) for run_info in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay verified KA59 push/bomb plans.")
    parser.add_argument("--target-level", type=int, default=max(PLANS))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = run(args.target_level, args.output_dir)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
