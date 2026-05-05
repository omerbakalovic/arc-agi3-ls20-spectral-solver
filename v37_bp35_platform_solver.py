"""
V37 - BP35 platform/gravity solver.

BP35 is a compact platformer hidden behind a dummy ARC sprite.  The useful
state is the internal tile grid: horizontal moves are followed by a gravity
fall, clicks toggle pass-through/solid cells, and purple gravity switches flip
the fall direction.  This runner stores the verified primitive plans and
replays them against the live ARC runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Sequence
import argparse
import json
import sys

import v16_signal_runner as score_utils


GAME_ID = "bp35"
OUTPUT_DIR = Path("v37_bp35_output")
Primitive = str


PLANS: Dict[int, List[Primitive]] = {
    1: "R R R R L L C5,19 C4,16 L C4,15 C4,12 R C5,9 L L".split(),
    2: (
        "R R R R R C8,36 C8,35 C5,29 C4,29 C3,29 C2,29 "
        "L L L L L L C2,28 R R R C5,24 C5,23 L L "
        "C3,20 C3,17 C3,16 C4,16 C5,16 C6,16 C7,16 C8,16 "
        "R R R R R C8,15 C8,14 L L L C5,9"
    ).split(),
    3: (
        "R C5,28 R R C6,27 C5,23 C4,23 C3,23 L L L L R R "
        "C5,17 C6,17 C5,18 C6,18 R R R C6,12 C5,12 C4,12 "
        "L L L L L C2,12 C5,7 R R R R R"
    ).split(),
    4: "R R C5,7 L L C3,17 L R R C5,23 R C3,23 R C7,23 C7,24 L L L C4,31".split(),
    5: (
        "R R C6,16 R C8,12 C8,21 R R L L L C3,21 L L C8,29 "
        "L R R R R C9,9 R R R C8,9 L C7,9 L L L"
    ).split(),
    6: (
        "R R R R R C6,22 C4,31 L L R R L L C5,13 L C4,13 L L "
        "R R R R C8,1 L L L C6,13 R R L L C6,25 C7,25 "
        "R R R R L L L L L L"
    ).split(),
    7: (
        "R R R C6,21 C0,5 R C0,6 R L L C0,7 L L C4,15 C0,8 L "
        "L R C0,9 R C4,9 C0,10 C5,10 R C5,10 C0,11 C6,9 R "
        "C6,9 C0,12 C7,4 C7,5 R R C0,13 R L L C0,14 "
        "L L L L C0,15"
    ).split(),
    8: (
        "C2,29 C3,29 C4,29 C5,29 C6,29 C7,29 R R R R "
        "C7,30 C8,30 R C8,29 C9,29 R C9,28 C9,27 C9,26 C9,25 "
        "C8,25 L C7,25 L L R C7,22 C3,18 C4,18 C5,18 L "
        "C6,18 C6,17 C7,17 R C8,18 C8,17 R C5,2 R"
    ).split(),
    9: (
        "C7,8 C6,8 C5,8 C4,8 C3,8 C3,7 C2,8 C1,8 C8,8 "
        "C6,31 R R L L L C3,26 C4,26 C5,31 C5,30 C5,29 C4,29 C4,28 C3,28 "
        "C0,25 C0,21 C0,33 C0,19 C0,35 C0,15 "
        "C3,27 C3,26 C3,25 C2,26 C2,25 C2,24 C2,23 C2,22 C2,21 "
        "C3,21 R C4,21 R C5,21 R C6,21 R C7,21 R "
        "C1,1 C7,22 C7,23 C8,23 R C9,23 R C2,1 "
        "C9,22 C9,21 C9,20 C9,19 C9,18 C9,17 C9,16 C9,15 "
        "C8,9 L C7,9 L C6,9 L C5,9 L C4,9 L C3,9 L C2,9 L "
        "C2,8 C1,8 L C0,8 L C3,1 "
        "C0,9 C0,10 C0,11 C0,12 C0,13 C0,14 C0,15 C0,16 "
        "C0,17 C0,18 C0,19 C0,20 C0,21 C0,22 C0,23 C0,24 "
        "C0,25 C0,26 C0,27 C0,28 C0,29 C0,30 C0,31 C0,32 "
        "C0,33 C0,34 C0,35 C0,36 C0,37 C0,38 C0,39 C0,40 "
        "C1,40 R R"
    ).split(),
}


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    plan: List[Primitive]
    final_position: tuple[int, int]
    gravity_up: bool
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


def grid_click_data(env, grid_x: int, grid_y: int) -> dict[str, int]:
    world = env._game.oztjzzyqoek
    return {
        "x": grid_x * 6 + 3,
        "y": grid_y * 6 + 3 - world.camera.rczgvgfsfb[1],
    }


def world_state(env) -> tuple[tuple[int, int], bool, bool, bool]:
    world = env._game.oztjzzyqoek
    return (
        tuple(world.twdpowducb.qumspquyus),
        bool(world.vivnprldht),
        bool(world.nkuphphdgrp),
        bool(world.jrhqdvdwpsb),
    )


def execute_primitive(env, game_action, primitive: Primitive):
    if primitive == "L":
        return env.step(game_action.ACTION3)
    if primitive == "R":
        return env.step(game_action.ACTION4)
    if primitive.startswith("C"):
        grid_x, grid_y = [int(item) for item in primitive[1:].split(",", 1)]
        return env.step(game_action.ACTION6, grid_click_data(env, grid_x, grid_y))
    raise ValueError(f"unknown primitive: {primitive}")


def execute_level(env, game_action, level: int, plan: Sequence[Primitive], write) -> LevelRun:
    start_pos, start_gravity, _, _ = world_state(env)
    write(f"  L{level} start pos={start_pos} gravity_up={start_gravity} actions={len(plan)}")

    used: List[Primitive] = []
    for primitive in plan:
        used.append(primitive)
        result = execute_primitive(env, game_action, primitive)
        pos, gravity_up, won_cell, lost_cell = world_state(env)
        state = getattr(result.state, "value", result.state)
        if int(getattr(result, "levels_completed", level - 1)) >= level:
            write(f"  completed L{level} after {len(used)} actions pos={pos} gravity_up={gravity_up}")
            return LevelRun(level, True, len(used), list(used), pos, gravity_up)
        if lost_cell or state not in {"NOT_FINISHED", "WIN"}:
            return LevelRun(
                level,
                False,
                len(used),
                list(used),
                pos,
                gravity_up,
                reason=f"primitive {primitive} ended in state={state} lost_cell={lost_cell} won_cell={won_cell}",
            )

    pos, gravity_up, won_cell, lost_cell = world_state(env)
    return LevelRun(
        level,
        False,
        len(used),
        list(used),
        pos,
        gravity_up,
        reason=f"plan exhausted won_cell={won_cell} lost_cell={lost_cell}",
    )


def run_solver(target_level: int, output_dir: Path) -> int:
    write, flush = log_sink(output_dir)
    runs: List[LevelRun] = []

    try:
        import arc_agi
        from arcengine import GameAction

        arc = arc_agi.Arcade()
        env = arc.make(GAME_ID, render_mode=None)
        write(f"V37 BP35 platform solver target=L{target_level}")
        score_utils.write_scorecard_snapshot(arc, write, "Initial score")

        for level in range(1, target_level + 1):
            plan = PLANS.get(level)
            if plan is None:
                raise RuntimeError(f"no verified plan for level {level}")
            run_info = execute_level(env, GameAction, level, plan, write)
            runs.append(run_info)
            score_utils.write_scorecard_snapshot(arc, write, f"Score after L{level}")
            if not run_info.success:
                write(f"  FAILED L{level}: {run_info.reason}")
                break

        completed = sum(1 for run in runs if run.success)
        total_actions = sum(run.actions for run in runs)
        write("")
        write(f"Summary: completed={completed}/{target_level} total_actions={total_actions}")
        (output_dir / "v37_bp35_results.json").write_text(
            json.dumps(
                {
                    "game_id": GAME_ID,
                    "target_level": target_level,
                    "completed": completed,
                    "total_actions": total_actions,
                    "runs": [asdict(run) for run in runs],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0 if completed == target_level else 1
    finally:
        flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay verified BP35 platform plans.")
    parser.add_argument("--target-level", type=int, default=max(PLANS), choices=range(1, max(PLANS) + 1))
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    return run_solver(args.target_level, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
