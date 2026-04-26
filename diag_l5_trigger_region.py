"""Probe the Level 5 rotation trigger cell around the first divergence."""
from __future__ import annotations

import numpy as np

import v15_level3_signal_planner as core
import v16_signal_runner as runner


def sprite_summary(sprite) -> str:
    tags = ",".join(sprite.tags or [])
    visible = getattr(sprite, "visible", getattr(sprite, "is_visible", None))
    return f"{sprite.name}@({sprite.x},{sprite.y}) tags=[{tags}] visible={visible}"


def cell_sprites(game, row: int, col: int):
    return [sprite_summary(s) for s in game.mrznumynfe(col, row, game.gisrhqpee, game.tbwnoxqgc)]


def state_line(env, result=None) -> str:
    game = env._game
    pos = (int(game.gudziatsk.y), int(game.gudziatsk.x))
    frame_pos = None
    if result is not None and result.frame:
        frame_pos = core.detect_player(np.array(result.frame[0]))
    return (
        f"pos={pos} frame_pos={frame_pos} "
        f"shape={game.fwckfzsyc} "
        f"color={game.tnkekoeuk[game.hiaauhahz]}#{game.hiaauhahz} "
        f"rot={game.dhksvilbb[game.cklxociuu]}#{game.cklxociuu} "
        f"energy={game._step_counter_ui.current_steps}"
    )


def run() -> None:
    arc_module, _ = core.ensure_arc_runtime()
    arc = arc_module.Arcade()
    env = arc.make(core.GAME_ID, render_mode=None)
    core.do_l1(env)
    core.solve_l2(env)

    for level in (3, 4):
        for action in runner.warmup_for_level(level):
            env.step(core.action_map()[action])
        model = core.build_model(level, seed_moves=runner.model_seed_for_level(level))
        plan, _ = core.find_plan(model)
        for action in plan:
            result = env.step(core.action_map()[action])
            if int(result.levels_completed) >= level:
                break

    model = core.build_model(5, seed_moves=runner.model_seed_for_level(5))
    plan, trace = core.find_plan(model)
    act = core.action_map()
    print("wsoslqeku count", len(env._game.wsoslqeku))
    print("initial rotation sprites", [sprite_summary(s) for s in env._game.current_level.get_sprites_by_tag("rhsxkxzdjz")])
    for i, action in enumerate(plan, 1):
        if 31 <= i <= 37:
            print(f"before [{i:02d}] {action}", state_line(env))
            print("  target cell sprites", cell_sprites(env._game, 35, 14))
            print("  rotation sprites", [sprite_summary(s) for s in env._game.current_level.get_sprites_by_tag("rhsxkxzdjz")])
        result = env.step(act[action])
        if 31 <= i <= 37:
            print(f"after  [{i:02d}] {action}", state_line(env, result))
            print("  target cell sprites", cell_sprites(env._game, 35, 14))
            print("  rotation sprites", [sprite_summary(s) for s in env._game.current_level.get_sprites_by_tag("rhsxkxzdjz")])


if __name__ == "__main__":
    run()
