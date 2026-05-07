# BlackBox Agent

Milestone 1 turns the solved-game notebooks into a reusable black-box loop.
The agent only consumes reset/step frames and action deltas.  It does not read
level source, sprite tags, object IDs, or hand-authored coordinates.

## Implemented

- `TraceLogger`: writes JSONL/text traces, summaries, and optional `.npy` frame
  snapshots under `blackbox_runs/`.
- `Perception`: extracts palette counts, connected components, frame hashes,
  and before/after delta features.
- `ProbeRunner`: resets environments, probes keyboard actions, and records
  frame deltas from the public step result.
- `MovementModel`: infers actor-like motion from added/erased pixel centroids,
  estimates action vectors, detects likely collisions, and maintains a pixel
  step estimate.
- `HazardModel`: records terminal edges from failed attempts and forbids those
  abstract edges on later attempts.
- `PartialGraph` plus `BFSPlanner`: records visited abstract cells, movement
  edges, blocked actions, and navigates to frontiers or visible target
  estimates when reachable.
- `BlackBoxAgent`: probes actions, explores LS20 from frames/deltas, logs every
  decision, retries from reset with learned hazards, and resets the abstract
  graph when a level is completed.
- `ClickKernelModel`: intentionally present as a stub only.

Run:

```powershell
python -u .\v41_blackbox_ls20_agent.py --game ls20 --max-steps 260
```

Multiple attempts keep learned action vectors and terminal-edge hazards:

```powershell
python -u .\v41_blackbox_ls20_agent.py --game ls20 --max-steps 180 --attempts 2 --no-save-frames
```

For a quicker smoke test without frame arrays:

```powershell
python -u .\v41_blackbox_ls20_agent.py --game ls20 --max-steps 40 --attempts 1 --no-save-frames
```

## Current LS20 Smoke Result

The current two-attempt smoke run is useful but still not a solve:

```text
python -u .\v41_blackbox_ls20_agent.py --game ls20 --max-steps 180 --attempts 2 --no-save-frames

attempt 1: GAME_OVER after 132 live actions
learned hazard: level 0, pos=(-7, -3), action=2
attempt 2: reached max step limit without dying
graph after attempt 2: visited=112, edges=228, walls=56, forbidden=1
action vectors: 1=(-1,0), 2=(1,0), 3=(0,-1), 4=(0,1)
pixel_step_estimate: 5.0
levels_completed: 0
```

Longer runs keep accumulating terminal-edge evidence:

```text
python -u .\v41_blackbox_ls20_agent.py --game ls20 --max-steps 300 --attempts 3 --no-save-frames

attempt 1: GAME_OVER after 132 live actions
attempt 2: GAME_OVER after 225 live actions
attempt 3: GAME_OVER after 225 live actions
learned hazards: 3 terminal edges on level 0
largest graph: visited=132, edges=275, walls=72, forbidden=3
levels_completed: 0
```

This is a better black-box explorer, not yet a level solver.

## Current Limitations

- Current LS20 validation is an attempt, not a solve. The agent now learns one
  terminal-edge hazard and avoids it on the next attempt, but it still does not
  complete level 1.
- Movement detection is based on local added/erased pixel centroids. It can
  confuse animation, rotation, teleport, or large environmental changes with
  movement.
- LS20-style rolling movement is handled by tracking local delta-cluster
  centroids across repeated probes, but this is still a heuristic rather than a
  full actor segmentation model.
- The graph is abstract and partial. It learns from successful/blocked actions
  but does not reconstruct the full visible map yet.
- Target detection is only a rarity-based component heuristic. It is useful for
  logging and rough exploration bias, not reliable goal semantics.
- The planner explores frontiers with BFS over known edges. It does not yet
  infer keys, doors, switches, shape changes, gravity, portals, click kernels,
  or multi-step object operators.
- Hazard memory is local to the run. It is not persisted across CLI invocations.
- `ClickKernelModel` is a stub. Click puzzles are intentionally out of scope
  for Milestone 1.
- The first goal is evidence collection and LS20 movement attempts, not a
  claim of a finished general ARC-AGI-3 solver.
