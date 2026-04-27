# ARC-AGI-3 LS20 Spectral Signal Solver

This repository contains experimental, math-first solvers for public ARC-AGI-3
environments.

The central idea is to treat each level as a graphical/mathematical signal:
walkable cells form a graph, visual objects become state-transition operators,
and planning happens in an augmented state space containing position, shape,
color, rotation, energy, collectibles, multi-goal completion, and moving
effects.

## Current Results

On the public `ls20` environment version `9607627b`, the LS20 runner solves all
available levels:

```text
environment: ls20-9607627b
score: 100.0
levels_completed: 7 / 7
state: WIN
total_actions: 334
level_actions: [16, 46, 42, 52, 48, 75, 55]
level_baseline_actions: [22, 123, 73, 84, 96, 192, 186]
```

On the public `tr87` environment version `cd924810`, the TR87 symbolic
transducer runner also solves all available levels:

```text
environment: tr87-cd924810
score: 100.0
levels_completed: 6 / 6
state: WIN
total_actions: 118
level_actions: [14, 25, 21, 21, 14, 23]
level_baseline_actions: [54, 58, 40, 45, 71, 146]
```

On the public `wa30` environment version `ee6fef47`, the WA30 object
manipulation runner also solves all available levels:

```text
environment: wa30-ee6fef47
score: 100.0
levels_completed: 9 / 9
state: WIN
total_actions: 616
level_actions: [26, 61, 76, 47, 117, 50, 36, 143, 60]
level_baseline_actions: [71, 119, 183, 98, 368, 68, 79, 442, 415]
```

The latest local reproduction summary is documented in
[`docs/RESULTS.md`](docs/RESULTS.md).

## What This Is

- Reproducible 100.0-score solvers for public LS20, TR87, and WA30
  environments.
- A compact demonstration that symbolic/state-space modeling can solve
  interactive ARC-AGI-3 games without an LLM policy.
- A research artifact for spectral, graph, potential-field, and algebraic
  approaches to interactive ARC tasks.

## What This Is Not Yet

This is not yet a fully general ARC-AGI-3 agent.

The current runners are environment-specific and use the local ARC environment
source cache to parse symbolic structure. That makes them useful as transparent
research probes, but they should not be described as black-box competition
agents. To become a proper ARC-AGI-3 generalist, source parsers need to be
replaced by perception and dynamics inference from observations/actions only,
and the agent needs to be evaluated across multiple unseen games.

## Architecture

```text
frame -> perception -> graph/TDA -> operator model -> staged planner -> action
```

Important files:

- `v15_level3_signal_planner.py`: core parser and augmented-state planner.
- `v16_signal_runner.py`: generalized LS20 runner, scorecard logging, and
  end-to-end execution through all available levels.
- `v17_tr87_symbolic_solver.py`: TR87 symbolic transducer solver over rewrite
  rules, modulo-7 glyph operators, double translation, and tree translation.
- `v18_wa30_object_solver.py`: WA30 grab/drag object solver with helper
  cooperation, special-object staging, deadlock release, and final transport
  plans through all nine levels.
- `exotic/`: earlier math-first modules for perception, TDA, potential fields,
  group-state reasoning, temporal diffs, and state-machine experiments.
- `diag_model_divergence.py`: compares the planner model against live runtime
  traces.
- `diag_l5_trigger_region.py`: targeted probe for moving trigger behavior.

## Reproduce

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the solver:

```bash
python v16_signal_runner.py --target-level 8
python v17_tr87_symbolic_solver.py --target-level 6
python v18_wa30_object_solver.py --target-level 9
```

The public LS20 source currently contains 7 levels. Passing `--target-level 8`
is intentional: the runner detects that only 7 levels are available and solves
through level 7.

Outputs are written locally to:

```text
v16_signal_runner_output/target_L8/
v17_tr87_output/target_L6/
v18_wa30_output/target_L9/
```

These generated files are ignored by git.

## Publication Positioning

The honest claim is:

> Source-assisted symbolic/spectral planners solve public ARC-AGI-3 LS20,
> TR87, and WA30 environments with 100.0 scores, and provide a concrete
> research path toward black-box interactive world-modeling agents.

The claim to avoid is:

> This is a solved ARC-AGI-3 generalist.

The next research step is to remove source access and infer the same operator
model from frame deltas, action probes, and persistent memory.

## License

MIT for the code in this repository. ARC Prize environment files are not
vendored here and remain under their original terms.
