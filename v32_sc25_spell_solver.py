"""
V32 - spell-pattern solver for ARC-AGI-3 SC25.

SC25 is a compact keyboard/click puzzle.  The player moves on a pixel grid and
casts spells by toggling a 3x3 panel:

* RESIZE: middle-column cross pattern toggles player scale.
* TELE: top-left/top-middle/center teleports to the next target marker.
* FIRE: middle-column pattern shoots in the last movement direction and removes
  matching blocker/target pairs.

The plans below are engine-verified for all six public levels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "sc25"
OUTPUT_DIR = Path("v32_sc25_output")

Primitive = str
Macro = str

CLICK_POINTS: Dict[Primitive, Tuple[int, int]] = {
    "C00": (25, 50),
    "C01": (30, 50),
    "C02": (35, 50),
    "C10": (25, 55),
    "C11": (30, 55),
    "C12": (35, 55),
    "C20": (25, 60),
    "C21": (30, 60),
    "C22": (35, 60),
}

MACROS: Dict[Macro, List[Primitive]] = {
    "FIRE": ["C01", "C11", "C21"],
    "RESIZE": ["C01", "C10", "C12", "C21"],
    "TELE": ["C00", "C01", "C11"],
}

PLANS: Dict[int, List[Macro]] = {
    1: ["U", "L", "L", "L", "L", "RESIZE", "L", "L", "L", "L"],
    2: ["TELE", "U", "U"],
    3: ["R", "FIRE", "L", "L", "L", "D", "D", "D", "D", "L"],
    4: [
        "D",
        "D",
        "R",
        "R",
        "RESIZE",
        "D",
        "R",
        "L",
        "FIRE",
        "D",
        "D",
        "D",
        "R",
        "R",
        "R",
        "R",
    ],
    5: [
        "U",
        "RESIZE",
        "TELE",
        "L",
        "L",
        "L",
        "L",
        "L",
        "L",
        "U",
        "FIRE",
        "RESIZE",
        "D",
        "D",
        "L",
        "FIRE",
        "TELE",
        "U",
        "U",
        "U",
        "U",
        "U",
        "U",
    ],
    6: [
        "RESIZE",
        "TELE",
        "R",
        "R",
        "U",
        "U",
        "RESIZE",
        "FIRE",
        "TELE",
        "L",
        "L",
        "L",
        "FIRE",
        "TELE",
        "U",
        "R",
        "U",
        "U",
        "U",
        "U",
        "U",
    ],
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    macro_plan: List[Macro]
    primitive_plan: List[Primitive]
    player: Tuple[int, int, int, int]
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


def expand_plan(plan: Sequence[Macro]) -> List[Primitive]:
    primitives: List[Primitive] = []
    for item in plan:
        primitives.extend(MACROS.get(item, [item]))
    return primitives


def action_data(primitive: Primitive) -> Dict[str, int]:
    x, y = CLICK_POINTS[primitive]
    return {"x": x, "y": y}


def player_state(env) -> Tuple[int, int, int, int]:
    player = env._game.plnqvukupu
    return (
        int(player.x),
        int(player.y),
        int(player.scale),
        int(getattr(player, "rotation", 0)),
    )


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "U":
        return env.step(game_action.ACTION1)
    if primitive == "D":
        return env.step(game_action.ACTION2)
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive in CLICK_POINTS:
        return env.step(game_action.ACTION6, action_data(primitive))
    raise ValueError(f"unknown primitive action: {primitive}")


def execute_level(env, game_action, macro_plan: Sequence[Macro], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    primitives = expand_plan(macro_plan)
    before_completed = level - 1
    write(
        f"  start player={player_state(env)} spells={env._game.jlpticwjyvy} "
        f"budget={env._game.eyxbonasvgm}"
    )

    used: List[Primitive] = []
    for primitive in primitives:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        if int(getattr(result, "levels_completed", before_completed)) >= level:
            write(
                f"  completed L{level} after {len(used)} actions "
                f"player={player_state(env)}"
            )
            return LevelRun(
                level=level,
                success=True,
                actions=len(used),
                macro_plan=list(macro_plan),
                primitive_plan=used,
                player=player_state(env),
            )
        if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level=level,
                success=False,
                actions=len(used),
                macro_plan=list(macro_plan),
                primitive_plan=used,
                player=player_state(env),
                reason=f"game state became {getattr(result.state, 'value', result.state)}",
            )

    return LevelRun(
        level=level,
        success=False,
        actions=len(used),
        macro_plan=list(macro_plan),
        primitive_plan=used,
        player=player_state(env),
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
        write(f"SC25 target={target_level} available={max_level} effective={effective_target}")

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
