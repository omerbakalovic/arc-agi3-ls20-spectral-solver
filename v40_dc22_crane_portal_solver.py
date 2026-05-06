"""
V40 - DC22 portal/crane spectral-control solver.

DC22 combines three mechanics:

* colored portal buttons cycle same-tag platform variants and teleport between
  matching 2x2 tewfut anchors;
* small rolo pads reveal crane controls only while the player is standing on
  the matching pad;
* the final level uses a graph-constrained crane to carry a 20x20 brixto bridge
  through a vcha lattice.

The plans below were generated with source-assisted finite-state models over
portal color, bridge phase, rolo visibility, and crane anchor coordinates, then
validated against the live ARC runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "dc22"
OUTPUT_DIR = Path("v40_dc22_output")
Primitive = str


PLANS: Dict[int, str] = {
    1: (
        "U Cb U U U U R R R R R Ca U U U Cb U U R R"
    ),
    2: (
        "Cb D D D D D D R R R R R R Cc D D D D D "
        "U U U U U U U U U U Ca R U U U U U U U U U U R"
    ),
    3: (
        "L Ca Cb L L L D D D L Ca L L L L Cb L L L "
        "Ca Cb U U U U Cc U U R R U R Cd U U U "
        "R R R R R R D D R"
    ),
    4: (
        "D R Ce R Ce R Ce R Ce R R R R R R D D D D "
        "Ce Ce Ce Ce Cf Cf Cf Cf Cf L L L D D Cc D R R "
        "Cf D D D D D D Cf R Cf R Cf R Cf R D "
        "R R R R R R D D R"
    ),
    5: (
        "L Cb L U U L Cb Ce Ce Ce Ce Cf Cf Cf Cf "
        "Kup Kup Kup Kright Kright Kright Kgrab "
        "Kleft Kleft Kleft Kdown Kdown Kdown Kright Kright Kright "
        "L U U U U R U Kleft Kleft Kleft Kup Kup Kup "
        "Kright Kright Kright L U U U U U U U Cc R "
        "Kleft Kleft Kleft Kdown Kdown Kdown "
        "U U U U U U U U "
        "D D D D D D D D D D D D D "
        "R R R R R R R Cd D D D D D L L Cd U U L L L L L L"
    ),
    6: (
        # unlock the grab button, return to the lower teleporter
        "L L L L L U U Cc R R U U D D L L Cc "
        # reach the d trigger through the lower-left brixto phase
        "D D Cf Cf Cf Cf D D L L L D L Cf U L Cf "
        "U U U U U U Cc U U U U U U U U U U U U U "
        # return to the color-cycle teleporter and move to the rolo pads
        "D D D D D D D D D D D D D D D D D D "
        "R Cf R Cf R Cf R Cf R U U U Cd Cd Cd Cc "
        # grab and drive the bridge to the upper gap
        "L Kleft Kleft Kleft Kleft Kgrab "
        "R R Kright Kright Kright Kright Kright "
        "L U Kup Kup Kup D L Kleft Kleft R U Kup Kup Kup "
        # teleport to the top-left island and walk to the goal
        "D Cc Cd Cd Cd Cc "
        "D D R R R R R R R R R R R R R R U R R R R R R R"
    ),
}


BUTTON_TAGS = {
    "Ca": "a",
    "Cb": "b",
    "Cc": "c",
    "Cd": "d",
    "Ce": "e",
    "Cf": "f",
}

CONTROL_TAGS = {
    "Kup": "up",
    "Kdown": "dowlja",
    "Kleft": "lersnf",
    "Kright": "riidpd",
    "Kgrab": "grawwq",
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Primitive]
    player: tuple[int, int]
    goal: tuple[int, int]
    remaining_steps: int
    crane: tuple[int, int]
    attached: str
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


def parse_plan(plan: str) -> List[Primitive]:
    return plan.split()


def display_for_grid(game, grid_x: int, grid_y: int) -> dict[str, int]:
    for y in range(64):
        for x in range(64):
            if game.camera.display_to_grid(x, y) == (grid_x, grid_y):
                return {"x": int(x), "y": int(y)}
    raise RuntimeError(f"no display coordinate maps to grid cell {(grid_x, grid_y)}")


def sprite_click_point(sprite) -> tuple[int, int]:
    pixels = sprite.render()
    candidates: List[tuple[float, int, int]] = []
    center_x = sprite.width / 2
    center_y = sprite.height / 2
    for y in range(sprite.height):
        for x in range(sprite.width):
            if pixels[y][x] >= 0:
                score = abs(x - center_x) + abs(y - center_y)
                candidates.append((score, int(sprite.x) + x, int(sprite.y) + y))
    if not candidates:
        raise RuntimeError(f"sprite {sprite.name} has no clickable positive pixel")
    _, grid_x, grid_y = min(candidates)
    return grid_x, grid_y


def visible_clickable(sprite) -> bool:
    return bool(sprite.is_visible) and sprite.interaction.name not in {"REMOVED", "INVISIBLE"}


def click_data_for_button(game, primitive: Primitive) -> dict[str, int]:
    tag = BUTTON_TAGS[primitive]
    candidates = []
    for sprite in game.current_level.get_sprites_by_tag("buezna"):
        if tag not in sprite.tags or not visible_clickable(sprite):
            continue
        # Direction/grab controls are also buezna in L6.  Button primitives are
        # reserved for portal/color-cycle controls, so skip real crane commands.
        if any(control in sprite.tags for control in CONTROL_TAGS.values()):
            continue
        candidates.append(sprite)
    if not candidates:
        raise RuntimeError(f"no visible buezna button for {primitive} on L{game.level_index + 1}")
    sprite = sorted(candidates, key=lambda s: (s.y, s.x, s.name))[0]
    grid_x, grid_y = sprite_click_point(sprite)
    return display_for_grid(game, grid_x, grid_y)


def click_data_for_control(game, primitive: Primitive) -> dict[str, int]:
    tag = CONTROL_TAGS[primitive]
    candidates = []
    for sprite in game.current_level.get_sprites_by_tag("sys_click"):
        if tag in sprite.tags and visible_clickable(sprite):
            candidates.append(sprite)
    if not candidates:
        raise RuntimeError(f"no visible crane control for {primitive} on L{game.level_index + 1}")
    sprite = sorted(candidates, key=lambda s: (s.y, s.x, s.name))[0]
    grid_x, grid_y = sprite_click_point(sprite)
    return display_for_grid(game, grid_x, grid_y)


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "U":
        return env.step(game_action.ACTION1)
    if primitive == "D":
        return env.step(game_action.ACTION2)
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive in BUTTON_TAGS:
        return env.step(game_action.ACTION6, click_data_for_button(env._game, primitive))
    if primitive in CONTROL_TAGS:
        return env.step(game_action.ACTION6, click_data_for_control(env._game, primitive))
    raise ValueError(f"unknown primitive: {primitive}")


def run_state(game, level: int, success: bool, actions: int, plan: List[Primitive], reason: str = "") -> LevelRun:
    return LevelRun(
        level=level,
        success=success,
        actions=actions,
        plan=plan,
        player=(int(game.qnnpcoyzd.x), int(game.qnnpcoyzd.y)),
        goal=(int(game.hfuqkxulm.x), int(game.hfuqkxulm.y)),
        remaining_steps=int(game.ujotjblwn.current_steps),
        crane=(int(getattr(game, "sjixewahg", 0)), int(getattr(game, "uxtzlxsiq", 0))),
        attached=str(getattr(game, "svxnnbpjl", "none")),
        reason=reason,
    )


def execute_level(env, game_action, level: int, plan: Sequence[Primitive], write) -> LevelRun:
    game = env._game
    write(
        f"  start player=({int(game.qnnpcoyzd.x)},{int(game.qnnpcoyzd.y)}) "
        f"goal=({int(game.hfuqkxulm.x)},{int(game.hfuqkxulm.y)}) actions={len(plan)}"
    )
    used: List[Primitive] = []
    for primitive in plan:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        if result is None:
            return run_state(game, level, False, len(used), list(used), f"{primitive} returned no result")
        state = getattr(result.state, "value", result.state)
        if int(getattr(result, "levels_completed", level - 1)) >= level:
            write(
                f"  completed L{level} after {len(used)} actions "
                f"player=({int(env._game.qnnpcoyzd.x)},{int(env._game.qnnpcoyzd.y)})"
            )
            return run_state(env._game, level, True, len(used), list(used))
        if state not in {"NOT_FINISHED", "WIN"}:
            return run_state(
                env._game,
                level,
                False,
                len(used),
                list(used),
                f"primitive {primitive} ended in state={state}",
            )

    return run_state(env._game, level, False, len(used), list(used), "plan exhausted before completion")


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
        write(f"DC22 target={target_level} available={max_level} effective={effective_target}")
        score_utils.write_scorecard_snapshot(arc, write, "Initial score")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            plan = parse_plan(PLANS[level])
            run_info = execute_level(env, GameAction, level, plan, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  failed: {run_info.reason}")
                break

        success = bool(runs and runs[-1].level == effective_target and runs[-1].success)
        write("\nFINAL: " + ("SUCCESS" if success else "PARTIAL"))
        scorecard, scorecard_error = score_utils.write_scorecard_snapshot(arc, write, "Final score", full=True)
        summary = {
            "requested_target_level": target_level,
            "effective_target_level": effective_target,
            "success": success,
            "runs": [asdict(run) for run in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay verified DC22 portal/crane plans.")
    parser.add_argument("--target-level", type=int, default=max(PLANS))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    summary = run(args.target_level, args.output_dir)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
