# ARC-AGI-3 LS20 Spectral Signal Solver

This repository contains an experimental, math-first solver for the public
ARC-AGI-3 environment `ls20`.

The central idea is to treat each level as a graphical/mathematical signal:
walkable cells form a graph, visual objects become state-transition operators,
and planning happens in an augmented state space containing position, shape,
color, rotation, energy, collectibles, multi-goal completion, and moving
effects.

## Current Result

On the public `ls20` environment version `9607627b`, the current runner solves
all available levels:

```text
score: 100.0
levels_completed: 7 / 7
state: WIN
total_actions: 334
level_actions: [16, 46, 42, 52, 48, 75, 55]
level_baseline_actions: [22, 123, 73, 84, 96, 192, 186]
```

The latest local reproduction summary is documented in
[`docs/RESULTS.md`](docs/RESULTS.md).

## What This Is

- A reproducible solver for the public LS20 environment.
- A compact demonstration that graph/state-space modeling can solve an
  interactive ARC-AGI-3 game without an LLM policy.
- A research artifact for spectral, graph, potential-field, and algebraic
  approaches to interactive ARC tasks.

## What This Is Not Yet

This is not yet a fully general ARC-AGI-3 agent.

The current `v16` runner is LS20-specific and uses the local ARC environment
source cache to parse level definitions. That makes it useful as a transparent
research probe, but it should not be described as a black-box competition agent.
To become a proper ARC-AGI-3 generalist, the source parser needs to be replaced
by perception and dynamics inference from observations/actions only, and the
agent needs to be evaluated across multiple unseen games.

## Architecture

```text
frame -> perception -> graph/TDA -> operator model -> staged planner -> action
```

Important files:

- `v15_level3_signal_planner.py`: core parser and augmented-state planner.
- `v16_signal_runner.py`: generalized LS20 runner, scorecard logging, and
  end-to-end execution through all available levels.
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
```

The public LS20 source currently contains 7 levels. Passing `--target-level 8`
is intentional: the runner detects that only 7 levels are available and solves
through level 7.

Outputs are written locally to:

```text
v16_signal_runner_output/target_L8/log.txt
v16_signal_runner_output/target_L8/summary.json
```

These generated files are ignored by git.

## Publication Positioning

The honest claim is:

> A source-assisted symbolic/spectral planner solves the public ARC-AGI-3 LS20
> environment 7/7 with a 100.0 score and provides a concrete research path
> toward black-box interactive world-modeling agents.

The claim to avoid is:

> This is a solved ARC-AGI-3 generalist.

The next research step is to remove source access and infer the same operator
model from frame deltas, action probes, and persistent memory.

## License

MIT for the code in this repository. ARC Prize environment files are not
vendored here and remain under their original terms.

