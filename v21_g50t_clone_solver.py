"""
V21 - clone/rewind keyboard solver for ARC-AGI-3 G50T.

G50T is a synchronous multi-agent puzzle.  ACTION5 rewinds the current
movement history, then turns that history into a clone track.  Later moves
advance the live player, old clones, and autonomous actors in lock-step.

The plans below were derived from the runtime object graph: pressure switches
drive moving gates, paired pads swap occupants, and autonomous actors can be
steered indirectly by opening their corridors at the right time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "g50t"
OUTPUT_DIR = Path("v21_g50t_output")

ACTION_CHARS = {
    "U": 1,
    "D": 2,
    "L": 3,
    "R": 4,
    "A": 5,
}


PLANS: Dict[int, str] = {
    1: "RRRRADDDDDDDRRRRR",
    2: "LLADDDDLLLLUULLAUUULLLLLLLDDRRR",
    3: (
        "UURRRRDDDDRA"
        "UURRRRRRRDDDDDDDLLLLL"
        "A"
        "UURRRRRRRDDDDDDDLLLLL"
        "LLUUURRUU"
    ),
    4: (
        "DDRDA"
        "DDRRUURRDDD"
        "A"
        "LLLDDDDDRRR"
        "LLL"
    ),
    5: (
        "UDDRRRDDD"
        "A"
        "DRRRUURRRDDDRRR"
        "A"
        "DRRRUURRRDDDDDR"
        "LDLLLLLUU"
    ),
    6: (
        "LLUA"
        "LLULLA"
        "LLDLLLLUULLLDDDDDRRU"
        "DLLUUUUURRRDDRRDDRR"
    ),
    7: (
        "DDLRUULLUU"
        "A"
        "DDRRUUUURRDDDDUUUULLLUURRR"
        "A"
        "DDRRUUUURRDDDD"
        "UDUDUDUDUDUD"
        "LLL"
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


def snapshot(game) -> Dict[str, object]:
    controller = game.vgwycxsxjz
    player = controller.dzxunlkwxt
    goal = controller.whftgckbcu
    return {
        "level_index": int(game.level_index) + 1,
        "player": [int(player.x), int(player.y)],
        "goal": [int(goal.x) + 1, int(goal.y) + 1],
        "phase": int(controller.rlazdofsxb),
        "history_len": len(controller.areahjypvy),
        "timer_x": int(game.twyixucrqi.x),
        "clones": [
            {"pos": [int(clone.x), int(clone.y)], "path_len": len(path)}
            for clone, path in controller.rloltuowth.items()
        ],
        "actors": [
            {"pos": [int(actor.x), int(actor.y)], "path_len": len(path)}
            for actor, path in controller.kgvnkyaimw.items()
        ],
        "outputs": [
            {
                "pos": [int(output.x), int(output.y)],
                "rotation": int(output.rotation),
                "active": bool(getattr(output, "dijhfchobv", False)),
            }
            for output in controller.uwxkstolmf
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
    write(f"  failed L{level}: plan exhausted at score {trace[-1]['levels_completed'] if trace else 'n/a'}")
    return False, trace


def run(target_level: int = 7) -> Dict[str, object]:
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
        write(f"G50T target={target_level} available={max_level} effective={effective_target}")

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
    parser = argparse.ArgumentParser(description="Replay the G50T clone/rewind solver.")
    parser.add_argument("--target-level", type=int, default=7)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
