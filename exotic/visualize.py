"""
Visualize the exotic stack — render each layer's output on real frames.

Panels:
  1) Raw frame + entity bounding boxes + grid overlay
  2) Walkable graph: nodes=cells, edges=4-adjacency; articulation pts highlighted
  3) Potential field φ as heatmap with gradient arrows
  4) Chosen trajectory overlaid on frame
"""
from __future__ import annotations
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import ListedColormap

from .perception import perceive
from .tda import compute_tda, classify_level, bridge_candidates
from .potential_field import FieldSpec, solve_laplace


# ls20 palette — approximate
PALETTE = np.array([
    [0, 0, 0],         # 0 black
    [30, 30, 30],
    [60, 60, 60],
    [255, 200, 60],    # 3 yellow (exit?)
    [120, 40, 40],
    [220, 60, 80],     # 5 red
    [40, 120, 200],
    [140, 200, 80],    # 7 green
    [200, 120, 220],
    [80, 220, 220],
    [180, 180, 180],
    [100, 100, 100],   # 11 grey (wall)
    [255, 255, 255],   # 12 white (player)
    [220, 220, 60],
    [40, 80, 40],
    [255, 120, 40],
], dtype=np.uint8)


def colorize(frame: np.ndarray) -> np.ndarray:
    f = np.clip(frame.astype(int), 0, 15)
    return PALETTE[f]


def plot_perception(ax, frame, pr, title="Perception"):
    ax.imshow(colorize(frame), interpolation='nearest')
    ax.set_title(title, fontsize=10)
    for e in pr.entities:
        r0, c0, r1, c1 = e.bbox
        # skip huge bg components
        if e.area > 500:
            continue
        rect = patches.Rectangle((c0 - 0.5, r0 - 0.5), c1 - c0 + 1,
                                 r1 - r0 + 1, linewidth=1,
                                 edgecolor='lime', facecolor='none')
        ax.add_patch(rect)
        ax.text(c0, r0 - 1, f"c{e.color}", color='lime',
                fontsize=6, ha='left', va='bottom')
    # HUD line
    ax.axhline(55, color='red', lw=0.5, linestyle='--')
    ax.set_xticks([]); ax.set_yticks([])


def plot_tda(ax, pr, sig, title="TDA"):
    ax.imshow(colorize(pr.frame), alpha=0.4, interpolation='nearest')
    # graph edges
    for (r, c) in pr.grid_walkable:
        for (dr, dc) in [(5, 0), (0, 5)]:
            nb = (r + dr, c + dc)
            if nb in pr.grid_walkable:
                ax.plot([c + 2, nb[1] + 2], [r + 2, nb[0] + 2],
                        color='cyan', lw=0.6, alpha=0.7)
    # component colors
    comp_colors = ['lime', 'orange', 'magenta', 'yellow']
    for i, comp in enumerate(sig.components[:4]):
        col = comp_colors[i]
        for (r, c) in comp:
            ax.plot(c + 2, r + 2, 'o', color=col, markersize=3)
    # articulation points
    for (r, c) in sig.articulation_cells:
        ax.plot(c + 2, r + 2, 's', color='red', markersize=5,
                markerfacecolor='none', markeredgewidth=1.2)
    ax.set_title(f"{title} | {sig.summary()}\narch={classify_level(sig)}",
                 fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])


def plot_potential(ax, pr, pf, title="Potential φ"):
    # Build a dense 64x64 field for display
    grid = np.full((64, 64), np.nan)
    for (r, c), v in pf.phi.items():
        grid[r:r+5, c:c+5] = v
    im = ax.imshow(grid, cmap='coolwarm_r', interpolation='nearest')
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    # draw wall silhouette
    walls = (pr.frame == 11)
    ax.contour(walls.astype(float), levels=[0.5], colors='black',
               linewidths=0.5)
    # gradient arrows at cell centers
    for (r, c) in pr.grid_walkable:
        best_a, best_v = None, pf.phi.get((r, c), float('inf'))
        for a, dr, dc in [('U', -5, 0), ('D', 5, 0),
                          ('L', 0, -5), ('R', 0, 5)]:
            nb = (r + dr, c + dc)
            if nb in pf.phi and pf.phi[nb] < best_v:
                best_v = pf.phi[nb]
                best_a = a
        if best_a:
            dr, dc = {'U': (-2, 0), 'D': (2, 0),
                      'L': (0, -2), 'R': (0, 2)}[best_a]
            ax.arrow(c + 2, r + 2, dc, dr, head_width=1,
                     head_length=0.8, fc='black', ec='black', lw=0.3)
    ax.set_title(title, fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])


def plot_trajectory(ax, pr, pf, start, title="Trajectory"):
    ax.imshow(colorize(pr.frame), interpolation='nearest')
    pos = start
    visited = {pos}
    pts = [pos]
    for _ in range(150):
        a = pf.action_at(pos)
        if a is None:
            break
        dr, dc = {'U': (-5, 0), 'D': (5, 0),
                  'L': (0, -5), 'R': (0, 5)}[a]
        nxt = (pos[0] + dr, pos[1] + dc)
        if nxt in visited:
            break
        visited.add(nxt)
        pts.append(nxt)
        pos = nxt
        if pos == pf.spec.exit_cell:
            break
    xs = [p[1] + 2 for p in pts]
    ys = [p[0] + 2 for p in pts]
    ax.plot(xs, ys, '-o', color='yellow', markersize=3, lw=1.2)
    ax.plot(xs[0], ys[0], 'o', color='lime', markersize=8, label='start')
    ax.plot(xs[-1], ys[-1], '*', color='red', markersize=10, label='end')
    ax.legend(loc='upper right', fontsize=7)
    ax.set_title(f"{title} ({len(pts)-1} steps)", fontsize=10)
    ax.set_xticks([]); ax.set_yticks([])


def render(frame: np.ndarray, triggers: dict, collectibles: dict,
            exit_cell, start_cell, out_path: str):
    pr = perceive(frame)
    sig = compute_tda(pr.grid_walkable, pr.walkable_mask)
    spec = FieldSpec(
        walkable=pr.grid_walkable,
        exit_cell=exit_cell,
        triggers_remaining=triggers,
        collectibles_remaining=collectibles,
    )
    pf = solve_laplace(spec, max_iters=1500)

    fig, axs = plt.subplots(2, 2, figsize=(12, 11))
    plot_perception(axs[0, 0], frame, pr,
                     title="1. Perception — entities + grid")
    plot_tda(axs[0, 1], pr, sig, title="2. TDA — cell graph")
    plot_potential(axs[1, 0], pr, pf,
                    title="3. Potential Field φ (Laplace BVP)")
    plot_trajectory(axs[1, 1], pr, pf, start_cell,
                     title="4. Trajectory (steepest descent)")
    fig.suptitle("Exotic Solver Stack — layered view", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches='tight')
    plt.close(fig)
    return pr, sig, pf
