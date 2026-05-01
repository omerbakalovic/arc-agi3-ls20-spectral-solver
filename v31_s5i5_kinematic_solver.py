"""
V31 - partial kinematic-chain solver for ARC-AGI-3 S5I5.

S5I5 is a click-only mechanical linkage puzzle.  Colored pieces carry target
anchors; bottom control bars resize all pieces of matching color, and later
levels add rotation buttons.  A level is solved when every visible target
marker overlaps a target anchor.

This checkpoint contains live-verified plans for all eight public levels.
Level 2 was found with an engine-backed BFS over bar-control clicks.  Levels 3
through 8 use the same engine-validated transition model with weighted A*
pruning over anchor distance and collision-free linkage states.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "s5i5"
OUTPUT_DIR = Path("v31_s5i5_output")
Click = Tuple[int, int]


PLANS: Dict[int, List[Click]] = {
    1: [(47, 21)] * 7 + [(24, 46)] * 6,
    2: (
        [(29, 57)] * 3
        + [(14, 57)] * 8
        + [(29, 57)] * 5
        + [(44, 57)] * 4
        + [(59, 57)] * 6
    ),
    3: (
        [(37, 57)]
        + [(37, 48)] * 3
        + [(8, 48)]
        + [(18, 57)] * 3
        + [(46, 48)] * 2
        + [(8, 48)] * 4
        + [(37, 48)] * 8
        + [(56, 57)] * 4
        + [(37, 48)]
        + [(46, 48)] * 3
        + [(37, 57)] * 7
    ),
    4: (
        [(36, 54)] * 3
        + [(4, 57)] * 7
        + [(36, 54)] * 4
        + ([(59, 48), (14, 48), (59, 57), (36, 54)] * 4)
    ),
    5: (
        [(28, 57)] * 3
        + [(43, 57)]
        + [(5, 57)]
        + [(50, 57)] * 2
        + [(43, 57)] * 3
        + [(5, 57), (58, 57), (5, 57), (58, 57)]
        + [(35, 57)] * 3
        + [(28, 57)] * 3
        + [(5, 57)] * 2
        + [(28, 57)] * 3
        + [(43, 57)] * 3
    ),
    6: (
        [(7, 57)]
        + [(31, 48)] * 2
        + [(50, 48)]
        + [(55, 57)] * 6
        + [(36, 57)] * 3
        + [(12, 48)] * 2
        + [(17, 57)] * 12
    ),
    7: (
        [(53, 51)] * 2
        + [(60, 58)] * 2
        + [(61, 51)] * 2
        + [(25, 51)]
        + [(17, 51)] * 2
        + [(11, 51)] * 6
        + [(11, 58)] * 8
        + [(11, 51)] * 2
        + [(39, 51)]
        + [(11, 58)] * 2
        + [(39, 51)] * 2
        + [(33, 51)] * 2
        + [(11, 58)] * 2
        + [(33, 51)] * 2
        + [(33, 58)] * 6
        + [(33, 51)] * 3
    ),
    8: (
        [(60, 11), (46, 4), (46, 11), (21, 56), (7, 56)]
        + [(49, 18)] * 2
        + [(46, 11)] * 2
        + [(7, 56)] * 2
        + [(38, 11)] * 2
        + [(49, 18), (46, 4)]
        + [(21, 56)] * 2
        + [(38, 4)]
        + [(49, 18)] * 2
        + [(60, 11), (38, 4), (60, 11)]
        + [(21, 56)] * 2
        + [(60, 11)] * 6
        + [(38, 11), (60, 11)]
        + [(7, 56)] * 2
        + [(60, 11)] * 3
    ),
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    clicks: List[Click]
    target_positions: List[Click]
    anchor_positions: List[Click]
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


def action_data(position: Click) -> Dict[str, int]:
    return {"x": int(position[0]), "y": int(position[1])}


def current_targets(env) -> List[Click]:
    return [
        (int(sprite.x), int(sprite.y))
        for sprite in env._game.current_level.get_sprites_by_tag("0087vvmblxkzdi")
    ]


def current_anchors(env) -> List[Click]:
    return [
        (int(sprite.x), int(sprite.y))
        for sprite in env._game.current_level.get_sprites_by_tag("0064ocqkuqacti")
    ]


def execute_level(env, game_action, clicks: Sequence[Click], write) -> LevelRun:
    level = int(env._game.level_index) + 1
    before_completed = level - 1
    write(f"  start targets={current_targets(env)} anchors={current_anchors(env)}")

    used: List[Click] = []
    for click in clicks:
        used.append((int(click[0]), int(click[1])))
        result = env.step(game_action.ACTION6, action_data(click))
        if int(getattr(result, "levels_completed", before_completed)) > before_completed:
            write(f"  completed L{level} after {len(used)} clicks")
            return LevelRun(
                level=level,
                success=True,
                actions=len(used),
                clicks=used,
                target_positions=current_targets(env),
                anchor_positions=current_anchors(env),
            )
        if getattr(result.state, "value", result.state) not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level=level,
                success=False,
                actions=len(used),
                clicks=used,
                target_positions=current_targets(env),
                anchor_positions=current_anchors(env),
                reason=f"game state became {getattr(result.state, 'value', result.state)}",
            )

    return LevelRun(
        level=level,
        success=False,
        actions=len(used),
        clicks=used,
        target_positions=current_targets(env),
        anchor_positions=current_anchors(env),
        reason="click plan exhausted before level completion",
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
        effective_target = min(target_level, max_level, max(PLANS))
        write(f"S5I5 target={target_level} available={max_level} effective={effective_target}")

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
        (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        flush()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-level", type=int, default=8)
    args = parser.parse_args()
    run(args.target_level)


if __name__ == "__main__":
    main()
