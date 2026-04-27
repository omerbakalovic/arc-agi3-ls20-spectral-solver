"""
V22 - shape/color signal solver for ARC-AGI-3 RE86.

RE86 is a sparse target-composition puzzle.  Movable sprites are treated as
geometric signals: their non-empty pixels must cover the colored target
constraints while avoiding wrong-color overlaps.  Later levels add color pads
and obstacle-driven shape deformation, so the final plans combine transport,
recoloring, cross-axis shifts, and rectangle resizing before replaying against
the real ARC runtime.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "re86"
OUTPUT_DIR = Path("v22_re86_output")

ACTION_CHARS = {
    "U": 1,
    "D": 2,
    "L": 3,
    "R": 4,
    "A": 5,
}


PLANS: Dict[int, str] = {
    1: "RRRRUUUUUUUALLUUUUUU",
    2: "LLLDDDDDDDDDDALLLLLLUUUUUUALLLLLLLDD",
    3: (
        "LUUUUUUUUUUUUU"
        "A"
        "RRRRRRRRUUUUUUUU"
        "A"
        "LLLLLLLLLUUUUUU"
    ),
    4: (
        "UUUUULLLLLLLDDDLLLLLL"
        "A"
        "DDDDDDDDRRRRRRUUUUUL"
    ),
    5: (
        "ULLDRUUUUUUUUURRR"
        "A"
        "DDDDDDDDDDRRRRRRRUUUU"
        "A"
        "DDDDDDDLLLLLLLLLLLURRRR"
    ),
    6: (
        "UURRDRDRRRRRRRULRRR"
        "A"
        "DDDDDLLULDDUUUUUULLLLLLLLL"
    ),
    7: (
        "UUUURRRUUULUUUURRRDRRRRRRDDDDDDD"
        "A"
        "UUUUUUUUUUUUURDDDDDURRRRRRRR"
        "A"
        "UUUUUURRRRLLLLLLLLLUUURDUUUUUUURRDDD"
    ),
    8: (
        "LLLDDDUUUUUUUUUUULLLLLLLURRRRRRRRUUUURRRDRRDRRDD"
        "LLLDDDDDDDDDLLLDDDDLLLLLLLL"
        "A"
        "UUUUUUUUUUUUUUDLLLLLLLLLLLLDDRRRRRRRRRUUUURRRDRRDRRDD"
        "LLLDDDDDDDDDLLLDLLLDLLLLLL"
    ),
}


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


def action_enum(game_action, ch: str):
    return getattr(game_action, f"ACTION{ACTION_CHARS[ch]}")


def sprite_color(sprite) -> int | None:
    values = [
        int(value)
        for value in sprite.pixels.flatten()
        if int(value) not in (-1, 0)
    ]
    if not values:
        return None
    return max(set(values), key=values.count)


def sprite_snapshot(sprite) -> Dict[str, object]:
    center_y = int(sprite.height) // 2
    center_x = int(sprite.width) // 2
    return {
        "name": str(sprite.name),
        "pos": [int(sprite.x), int(sprite.y)],
        "size": [int(sprite.width), int(sprite.height)],
        "color": sprite_color(sprite),
        "center": int(sprite.pixels[center_y, center_x]),
        "tags": sorted(str(tag) for tag in getattr(sprite, "tags", [])),
    }


def snapshot(game) -> Dict[str, object]:
    return {
        "level_index": int(game.level_index) + 1,
        "steps_left": int(game.xikvflgqgp.current_steps),
        "movers": [
            sprite_snapshot(sprite)
            for sprite in game.current_level.get_sprites_by_tag("0031cppcuvqlbi")
        ],
    }


def execute_level(env, game_action, plan: Sequence[str], write) -> Tuple[bool, List[Dict[str, object]]]:
    level = int(env._game.level_index) + 1
    trace: List[Dict[str, object]] = []
    for step_index, ch in enumerate(plan, 1):
        before = snapshot(env._game)
        result = env.step(action_enum(game_action, ch), {})
        after = snapshot(env._game)
        trace.append(
            {
                "step": step_index,
                "action": ch,
                "before": before,
                "after": after,
                "levels_completed": int(result.levels_completed),
            }
        )
        if int(result.levels_completed) >= level:
            write(f"  completed L{level} at step {step_index}/{len(plan)}")
            return True, trace
        if not result.frame:
            write(f"  failed L{level}: empty frame after step {step_index}")
            return False, trace
    write(f"  failed L{level}: plan exhausted")
    return False, trace


def run(target_level: int = 8) -> Dict[str, object]:
    output_dir = OUTPUT_DIR / f"target_L{target_level}"
    write, flush = log_sink(output_dir)
    runs: List[Dict[str, object]] = []
    scorecard = None
    scorecard_error = None
    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        max_level = len(env._game._levels)
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"RE86 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            plan = PLANS[level]
            write(f"\n=== Level {level} ===")
            write(f"plan_len={len(plan)} plan={plan}")
            ok, trace = execute_level(env, GameAction, plan, write)
            runs.append(
                {
                    "level": level,
                    "success": ok,
                    "actions": len(trace),
                    "plan": plan,
                    "trace": trace,
                }
            )
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
            "total_actions": sum(run["actions"] for run in runs),
            "scorecard": scorecard,
            "scorecard_error": scorecard_error,
        }
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay the RE86 shape/color solver.")
    parser.add_argument("--target-level", type=int, default=8)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
