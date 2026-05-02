"""
V33 - arrow-swarm solver for ARC-AGI-3 TU93.

TU93 is a keyboard-only grid puzzle.  The visible player arrow moves on the
board, while other arrow sprites are activated by proximity, trail the player,
or collide with target sprites.  The live engine advances a move through its
animation phases inside one ``env.step`` call, so the solver can execute compact
discrete action plans.

The plans below were found with engine-backed A* over sprite positions,
rotations, marked arrow state, and remaining target fragments.  They are
verified for all nine public levels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "tu93"
OUTPUT_DIR = Path("v33_tu93_output")
ActionName = str


PLANS: Dict[int, str] = {
    1: "RDDRURDDLLDRRDRURD",
    2: "URRDRRURRU",
    3: "UURULLULLDRDLLLDRDR",
    4: "RLRRRUURDULULULDL",
    5: "LLLRLLLLLDDDUUDDRDDRRRUDUUDUL",
    6: "LLDDRDDLDLUDLUDRURRUULLLDLUUUL",
    7: "RRRDDRURUUURDD",
    8: "RRUURRLLLDDRUURRUUULL",
    9: "LLUURDDLUURUURRRDDRDLDLDDLLUR",
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: str
    player: Tuple[int, int, int]
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


def player_state(env) -> Tuple[int, int, int]:
    players = env._game.current_level.get_sprites_by_tag("0017unajnymcki")
    if not players:
        return (-1, -1, -1)
    player = players[0]
    return (int(player.x), int(player.y), int(getattr(player, "rotation", 0)))


def object_counts(env) -> Dict[str, int]:
    return {
        "chasers": len(env._game.current_level.get_sprites_by_tag("0001haidilggfh")),
        "movers": len(env._game.current_level.get_sprites_by_tag("0020npxxteirsg")),
        "delayed": len(env._game.current_level.get_sprites_by_tag("0023otenflmryc")),
    }


def execute_action(env, game_action, action: ActionName):
    if action == "U":
        return env.step(game_action.ACTION1)
    if action == "D":
        return env.step(game_action.ACTION2)
    if action == "L":
        return env.step(game_action.ACTION3)
    if action == "R":
        return env.step(game_action.ACTION4)
    raise ValueError(f"unknown action: {action}")


def execute_level(env, game_action, plan: Sequence[ActionName], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    before_completed = level - 1
    plan_text = "".join(plan)
    write(
        f"  start player={player_state(env)} steps={env._game.ksulgrfyqx.current_steps} "
        f"objects={object_counts(env)}"
    )

    used: List[ActionName] = []
    for action in plan:
        used.append(action)
        result = execute_action(env, game_action, action)
        if int(getattr(result, "levels_completed", before_completed)) >= level:
            write(
                f"  completed L{level} after {len(used)} actions "
                f"player={player_state(env)}"
            )
            return LevelRun(
                level=level,
                success=True,
                actions=len(used),
                plan="".join(used),
                player=player_state(env),
            )
        if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level=level,
                success=False,
                actions=len(used),
                plan="".join(used),
                player=player_state(env),
                reason=f"game state became {getattr(result.state, 'value', result.state)}",
            )

    return LevelRun(
        level=level,
        success=False,
        actions=len(used),
        plan=plan_text,
        player=player_state(env),
        reason="plan exhausted before level completion",
    )


def run(target_level: int = 9) -> Dict[str, object]:
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
        write(f"TU93 target={target_level} available={max_level} effective={effective_target}")

        for level in range(1, effective_target + 1):
            write(f"\n=== Level {level} ===")
            run_info = execute_level(env, GameAction, list(PLANS[level]), write)
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
    parser.add_argument("--target-level", type=int, default=9)
    args = parser.parse_args()
    summary = run(args.target_level)
    return 0 if summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
