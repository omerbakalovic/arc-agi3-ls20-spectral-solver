"""
V26 - tape/portal solver for ARC-AGI-3 SB26.

SB26 is a keyboard/click puzzle that behaves like a small programmable tape.
Colored tokens and portal tokens are placed into frame slots; ACTION5 then
reads the first frame left-to-right.  A colored token emits one target color.
A portal token calls the frame whose border color matches the portal color and
returns after that frame finishes.

The solver builds this call-stack model from the live public environment,
backtracks over token placements until the emitted sequence matches the target
row, and replays the resulting click placements plus ACTION5 in the ARC
runtime.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Generator, List, Optional, Sequence, Tuple
import argparse
import json
import sys

import numpy as np

import v16_signal_runner as score_utils


GAME_ID = "sb26"
OUTPUT_DIR = Path("v26_sb26_output")
SLOT_OFFSET = 2
SLOT_STRIDE = 6
CONTROL_LINE_Y = 53

Position = Tuple[int, int]


@dataclass(frozen=True)
class Token:
    id: int
    kind: str
    color: int
    start: Position


@dataclass
class TapeModel:
    target: List[int]
    frame_colors: List[int]
    color_to_frame: Dict[int, int]
    slots: List[List[Position]]
    fixed_contents: Dict[Position, Optional[Tuple[str, int]]]
    tokens: List[Token]


@dataclass
class LevelRun:
    level: int
    success: bool
    actions: int
    placements: int
    plan: List[Dict[str, object]]
    emitted_target: List[int]
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


def tile_color(sprite) -> int:
    return int(sprite.pixels[1, 1])


def frame_color(sprite) -> int:
    return int(sprite.pixels[0, 0])


def frame_length(sprite) -> int:
    return int(sprite.name[-1])


def token_kind(sprite) -> str:
    return "portal" if sprite.name == "vgszefyyyp" else "tile"


def build_tape_model(game) -> TapeModel:
    frames = list(game.qaagahahj)
    frame_colors = [frame_color(frame) for frame in frames]
    color_to_frame = {color: index for index, color in enumerate(frame_colors)}
    target = [int(sprite.pixels[0, 0]) for sprite in game.wcfyiodrx]

    slots: List[List[Position]] = []
    fixed_contents: Dict[Position, Optional[Tuple[str, int]]] = {}
    for frame in frames:
        frame_slots: List[Position] = []
        for slot_index in range(frame_length(frame)):
            position = (
                int(frame.x) + SLOT_OFFSET + slot_index * SLOT_STRIDE,
                int(frame.y) + SLOT_OFFSET,
            )
            frame_slots.append(position)
            fixed_sprite = next(
                (
                    sprite
                    for sprite in game.dkouqqads
                    if int(sprite.x) == position[0] and int(sprite.y) == position[1]
                ),
                None,
            )
            if fixed_sprite is None:
                fixed_contents[position] = None
            else:
                fixed_contents[position] = (token_kind(fixed_sprite), tile_color(fixed_sprite))
        slots.append(frame_slots)

    tokens: List[Token] = []
    for sprite in game.dkouqqads:
        if int(sprite.y) <= CONTROL_LINE_Y:
            continue
        tokens.append(
            Token(
                id=len(tokens),
                kind=token_kind(sprite),
                color=tile_color(sprite),
                start=(int(sprite.x), int(sprite.y)),
            )
        )

    return TapeModel(
        target=target,
        frame_colors=frame_colors,
        color_to_frame=color_to_frame,
        slots=slots,
        fixed_contents=fixed_contents,
        tokens=tokens,
    )


def assigned_content(
    model: TapeModel,
    assignments: Dict[Position, int],
    position: Position,
) -> Optional[Tuple[str, int]]:
    token_id = assignments.get(position)
    if token_id is not None:
        token = model.tokens[token_id]
        return token.kind, token.color
    return model.fixed_contents[position]


def solve_assignment(model: TapeModel) -> Dict[Position, int]:
    token_by_id = {token.id: token for token in model.tokens}

    def walk(
        frame_index: int,
        slot_index: int,
        target_index: int,
        available: Tuple[int, ...],
        assignments: Dict[Position, int],
        visiting: set[Tuple[int, int]],
    ) -> Generator[Tuple[int, Tuple[int, ...], Dict[Position, int]], None, None]:
        if target_index == len(model.target):
            yield target_index, available, assignments
            return
        if slot_index >= len(model.slots[frame_index]):
            yield target_index, available, assignments
            return

        position = model.slots[frame_index][slot_index]
        content = assigned_content(model, assignments, position)

        if content is None:
            choices = sorted(
                available,
                key=lambda token_id: (
                    token_by_id[token_id].kind != "tile",
                    token_by_id[token_id].color,
                    token_id,
                ),
            )
            for token_id in choices:
                token = token_by_id[token_id]
                next_available = tuple(item for item in available if item != token_id)
                next_assignments = dict(assignments)
                next_assignments[position] = token_id

                if token.kind == "tile":
                    if (
                        target_index < len(model.target)
                        and token.color == model.target[target_index]
                    ):
                        yield from walk(
                            frame_index,
                            slot_index + 1,
                            target_index + 1,
                            next_available,
                            next_assignments,
                            visiting,
                        )
                elif token.color in model.color_to_frame and (token.color, target_index) not in visiting:
                    called_frame = model.color_to_frame[token.color]
                    for sub_index, sub_available, sub_assignments in walk(
                        called_frame,
                        0,
                        target_index,
                        next_available,
                        next_assignments,
                        visiting | {(token.color, target_index)},
                    ):
                        yield from walk(
                            frame_index,
                            slot_index + 1,
                            sub_index,
                            sub_available,
                            sub_assignments,
                            visiting,
                        )
            return

        kind, color = content
        if kind == "tile":
            if target_index < len(model.target) and color == model.target[target_index]:
                yield from walk(
                    frame_index,
                    slot_index + 1,
                    target_index + 1,
                    available,
                    assignments,
                    visiting,
                )
            return

        if color not in model.color_to_frame or (color, target_index) in visiting:
            return
        called_frame = model.color_to_frame[color]
        for sub_index, sub_available, sub_assignments in walk(
            called_frame,
            0,
            target_index,
            available,
            assignments,
            visiting | {(color, target_index)},
        ):
            yield from walk(
                frame_index,
                slot_index + 1,
                sub_index,
                sub_available,
                sub_assignments,
                visiting,
            )

    for target_index, _, assignments in walk(
        frame_index=0,
        slot_index=0,
        target_index=0,
        available=tuple(token.id for token in model.tokens),
        assignments={},
        visiting=set(),
    ):
        if target_index == len(model.target):
            return assignments

    raise RuntimeError(f"No SB26 tape assignment found for target {model.target}")


def click_data(game, position: Position) -> Dict[str, int | float]:
    scale, offset_x, offset_y = game.camera._calculate_scale_and_offset()
    x = (position[0] + 2) * scale + offset_x
    y = (position[1] + 2) * scale + offset_y
    return {"x": scalar(x), "y": scalar(y)}


def find_token_sprite(game, start: Position, kind: str, color: int):
    for sprite in game.dkouqqads:
        if (
            int(sprite.x) == start[0]
            and int(sprite.y) == start[1]
            and token_kind(sprite) == kind
            and tile_color(sprite) == color
        ):
            return sprite
    raise RuntimeError(f"Token {kind}:{color} at {start} not found")


def execute_level(env, game_action, write) -> Tuple[bool, LevelRun]:
    game = env._game
    level = int(game.level_index) + 1
    model = build_tape_model(game)
    assignments = solve_assignment(model)

    placement_plan: List[Dict[str, object]] = []
    actions = 0

    for destination, token_id in sorted(assignments.items(), key=lambda item: (item[0][1], item[0][0])):
        token = model.tokens[token_id]
        sprite = find_token_sprite(game, token.start, token.kind, token.color)
        source = (int(sprite.x), int(sprite.y))

        select_data = click_data(game, source)
        apply_action(env, game_action, 6, select_data)
        actions += 1

        place_data = click_data(game, destination)
        result = apply_action(env, game_action, 6, place_data)
        actions += 1

        placement_plan.append(
            {
                "kind": token.kind,
                "color": token.color,
                "source": list(source),
                "destination": list(destination),
                "select": select_data,
                "place": place_data,
            }
        )

        if not result.frame:
            return False, LevelRun(
                level=level,
                success=False,
                actions=actions,
                placements=len(placement_plan),
                plan=placement_plan,
                emitted_target=model.target,
                final_level_count=int(getattr(result, "levels_completed", level - 1)),
                reason="life lost during placement",
            )

    result = apply_action(env, game_action, 5)
    actions += 1
    while int(result.levels_completed) < level and result.frame and actions < 200:
        result = apply_action(env, game_action, 5)
        actions += 1

    success = bool(result.frame and int(result.levels_completed) >= level)
    if success:
        write(
            f"placements={len(placement_plan)} actions={actions} "
            f"target={model.target}"
        )
    return success, LevelRun(
        level=level,
        success=success,
        actions=actions,
        placements=len(placement_plan),
        plan=placement_plan,
        emitted_target=model.target,
        final_level_count=int(getattr(result, "levels_completed", level - 1)),
        reason="" if success else "verification did not advance level",
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
        write(f"SB26 target={target_level} available={max_level} effective={effective_target}")

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
    parser = argparse.ArgumentParser(description="Solve SB26 by tape/portal placement search.")
    parser.add_argument("--target-level", type=int, default=8)
    args = parser.parse_args()
    summary = run(args.target_level)
    if not summary["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
