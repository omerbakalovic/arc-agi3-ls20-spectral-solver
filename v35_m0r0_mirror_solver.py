"""
V35 - mirror-token solver for ARC-AGI-3 M0R0.

M0R0 is a paired-token puzzle.  The left token follows horizontal input, while
the right token mirrors horizontal input and shares vertical input.  Some
levels add movable one-cell blockers (`mosdlc`) that can be selected by click
and repositioned to break the symmetry.  Colored gate bars disappear when a
token reaches a matching one-cell key.

The plans below were found with a compact symbolic model over token positions,
movable blockers, hazards, and gate/key state.  They are replayed here as real
keyboard/click actions against the live ARC runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "m0r0"
OUTPUT_DIR = Path("v35_m0r0_output")
Primitive = str


PLANS: Dict[int, List[Primitive]] = {
    1: "U L U R L U U U R U R U R U R".split(),
    2: "D L L L D D D R R U R R D D D D D R R D R U L".split(),
    3: (
        "C0@1,3 U R U B C2@8,6 R R R B C1@6,2 "
        "R U R R R R D D D L L U B U L L U U U R R R "
        "U U L L L L U U U U U R R D D D R R U U U R D R"
    ).split(),
    4: "U C0@5,5 L L D B R D D R R".split(),
    5: (
        "L L U U U L U R R R U U R U L L L L L U U U L "
        "U U U U U R R U U U U U L L L L"
    ).split(),
    6: (
        "U U C0@6,9 L U U L U U U U B R D D D L D D D "
        "C0@4,3 D D B R R D R R R R D D U U L U U R"
    ).split(),
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Primitive]
    pieces: List[Tuple[str, int, int, str]]
    blockers: List[Tuple[int, int]]
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


def grid_click_data(env, grid_x: int, grid_y: int) -> Dict[str, int]:
    grid_width, grid_height = env._game.current_level.grid_size or (64, 64)
    scale = min(64 // grid_width, 64 // grid_height)
    x_offset = (64 - grid_width * scale) // 2
    y_offset = (64 - grid_height * scale) // 2
    return {
        "x": int(grid_x * scale + x_offset + scale // 2),
        "y": int(grid_y * scale + y_offset + scale // 2),
    }


def pieces_state(env) -> List[Tuple[str, int, int, str]]:
    rows: List[Tuple[str, int, int, str]] = []
    for name in ("pikgci-toljda-leklkn", "pikgci-toljda-rivmdg"):
        sprites = env._game.current_level.get_sprites_by_name(name)
        if not sprites:
            continue
        sprite = sprites[0]
        interaction = getattr(sprite.interaction, "name", str(sprite.interaction))
        rows.append((name, int(sprite.x), int(sprite.y), interaction))
    return rows


def blockers_state(env) -> List[Tuple[int, int]]:
    return [
        (int(sprite.x), int(sprite.y))
        for sprite in env._game.current_level.get_sprites_by_name("mosdlc")
    ]


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "U":
        return env.step(game_action.ACTION1)
    if primitive == "D":
        return env.step(game_action.ACTION2)
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive == "B":
        return env.step(game_action.ACTION6, grid_click_data(env, 0, 0))
    if primitive.startswith("C"):
        _prefix, coords = primitive.split("@", 1)
        grid_x, grid_y = [int(item) for item in coords.split(",", 1)]
        return env.step(game_action.ACTION6, grid_click_data(env, grid_x, grid_y))
    raise ValueError(f"unknown primitive: {primitive}")


def execute_level(env, game_action, plan: Sequence[Primitive], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    before_completed = level - 1
    write(
        f"  start pieces={pieces_state(env)} blockers={blockers_state(env)} "
        f"steps={env._game.vtivsqjblkm.current_steps}"
    )

    used: List[Primitive] = []
    for primitive in plan:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        if int(getattr(result, "levels_completed", before_completed)) >= level:
            write(
                f"  completed L{level} after {len(used)} actions "
                f"pieces={pieces_state(env)} blockers={blockers_state(env)}"
            )
            return LevelRun(
                level=level,
                success=True,
                actions=len(used),
                plan=list(used),
                pieces=pieces_state(env),
                blockers=blockers_state(env),
            )
        if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level=level,
                success=False,
                actions=len(used),
                plan=list(used),
                pieces=pieces_state(env),
                blockers=blockers_state(env),
                reason=f"game state became {getattr(result.state, 'value', result.state)}",
            )

    return LevelRun(
        level=level,
        success=False,
        actions=len(used),
        plan=list(used),
        pieces=pieces_state(env),
        blockers=blockers_state(env),
        reason="plan exhausted before level completion",
    )


def run(target_level: int = 6) -> Dict[str, object]:
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
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"M0R0 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, PLANS[level], write)
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
            "runs": [asdict(run) for run in runs],
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )
        return summary
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=6)
    args = parser.parse_args()
    summary = run(args.target_level)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
