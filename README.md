# ARC-AGI-3 Spectral Signal Solvers

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

On the public `ft09` environment version `0d8bbf25`, the FT09 click-constraint
runner also solves all available levels:

```text
environment: ft09-0d8bbf25
score: 100.0
levels_completed: 6 / 6
state: WIN
total_actions: 75
level_actions: [4, 7, 14, 16, 21, 13]
level_baseline_actions: [43, 12, 23, 28, 65, 37]
```

On the public `vc33` environment version `5430563c`, the VC33 geometry
transport runner also solves all available levels:

```text
environment: vc33-5430563c
score: 100.0
levels_completed: 7 / 7
state: WIN
total_actions: 217
level_actions: [3, 7, 23, 21, 68, 20, 75]
level_baseline_actions: [7, 18, 44, 61, 131, 34, 152]
```

On the public `g50t` environment version `5849a774`, the G50T clone/rewind
keyboard runner also solves all available levels:

```text
environment: g50t-5849a774
score: 100.0
levels_completed: 7 / 7
state: WIN
total_actions: 309
level_actions: [17, 31, 64, 31, 50, 49, 67]
level_baseline_actions: [78, 175, 179, 230, 96, 54, 67]
```

On the public `re86` environment version `8af5384d`, the RE86 shape/color
signal runner also solves all available levels:

```text
environment: re86-8af5384d
score: 100.0
levels_completed: 8 / 8
state: WIN
total_actions: 507
level_actions: [20, 36, 47, 42, 63, 46, 98, 155]
level_baseline_actions: [26, 42, 86, 108, 189, 139, 424, 241]
```

On the public `cd82` environment version `fb555c5d`, the CD82 paint-primitive
solver also solves all available levels:

```text
environment: cd82-fb555c5d
score: 100.0
levels_completed: 6 / 6
state: WIN
total_actions: 70
level_actions: [5, 6, 16, 14, 13, 16]
level_baseline_actions: [55, 8, 41, 21, 23, 23]
```

On the public `r11l` environment version `495a7899`, the R11L centroid solver
also solves all available levels:

```text
environment: r11l-495a7899
score: 100.0
levels_completed: 6 / 6
state: WIN
total_actions: 73
level_actions: [4, 9, 11, 14, 17, 18]
level_baseline_actions: [22, 33, 51, 26, 52, 49]
```

On the public `lp85` environment version `305b61c3`, the LP85 permutation
solver also solves all available levels:

```text
environment: lp85-305b61c3
score: 100.0
levels_completed: 8 / 8
state: WIN
total_actions: 79
level_actions: [5, 8, 16, 12, 9, 19, 5, 5]
level_baseline_actions: [17, 38, 31, 16, 41, 60, 26, 159]
```

On the public `sb26` environment version `7fbdac44`, the SB26 tape/portal
solver also solves all available levels:

```text
environment: sb26-7fbdac44
score: 100.0
levels_completed: 8 / 8
state: WIN
total_actions: 124
level_actions: [9, 15, 15, 15, 17, 19, 17, 17]
level_baseline_actions: [18, 28, 18, 19, 31, 23, 58, 18]
```

On the public `su15` environment version `1944f8ab`, the SU15 click/particle
solver completes all nine levels:

```text
environment: su15-1944f8ab
score: 100.0
levels_completed: 9 / 9
state: WIN
total_actions: 101
level_actions: [8, 12, 17, 12, 18, 11, 6, 9, 8]
level_baseline_actions: [22, 42, 26, 115, 36, 31, 8, 40, 41]
```

On the public `tn36` environment version `ef4dde99`, the TN36 program-grid
solver completes all seven levels:

```text
environment: tn36-ef4dde99
score: 100.0
levels_completed: 7 / 7
state: WIN
total_actions: 92
level_actions: [7, 9, 9, 13, 16, 21, 17]
level_baseline_actions: [32, 72, 26, 40, 30, 55, 62]
```

On the public `cn04` environment version `2fe56bfb`, the CN04 sprite-alignment
solver completes all six levels:

```text
environment: cn04-2fe56bfb
score: 100.0
levels_completed: 6 / 6
state: WIN
total_actions: 262
level_actions: [13, 39, 31, 52, 65, 62]
level_baseline_actions: [29, 54, 85, 300, 208, 113]
```

On the public `lf52` environment version `271a04aa`, the LF52 peg/conveyor
solver currently completes the first six of ten levels:

```text
environment: lf52-271a04aa
score: 38.18181818181818
levels_completed: 6 / 10
state: NOT_FINISHED
total_actions: 305
level_actions: [8, 34, 45, 50, 83, 85, 0, 0, 0, 0]
level_baseline_actions: [32, 81, 60, 71, 205, 148, 244, 109, 164, 225]
```

On the public `s5i5` environment version `18d95033`, the S5I5 kinematic-chain
solver completes all eight levels:

```text
environment: s5i5-18d95033
score: 100.0
levels_completed: 8 / 8
state: WIN
total_actions: 244
level_actions: [13, 26, 37, 30, 28, 27, 45, 38]
level_baseline_actions: [20, 89, 106, 54, 162, 38, 86, 83]
```

The latest local reproduction summary is documented in
[`docs/RESULTS.md`](docs/RESULTS.md).

## What This Is

- Reproducible 100.0-score solvers for public LS20, TR87, WA30, FT09, VC33,
  G50T, RE86, CD82, R11L, LP85, SB26, SU15, TN36, CN04, and S5I5 environments.
- A partial LF52 peg/conveyor solver that verifies the first six levels and
  exposes level 7 as the next long-horizon planning target.
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
- `v19_ft09_constraint_solver.py`: FT09 click/constraint solver over
  modulo-color operators, clue constraints, and GF(2)/center-only solutions.
- `v20_vc33_geometry_solver.py`: VC33 click geometry solver over platform
  mass-transfer operators, bridge swaps, marker transport, and exact replay.
- `v21_g50t_clone_solver.py`: G50T keyboard solver over rewind-created clone
  tracks, pressure gates, swap pads, autonomous actors, and synchronized
  replay.
- `v22_re86_shape_solver.py`: RE86 shape/color solver over sparse target
  masks, color pads, obstacle-driven rectangle resizing, and cross-axis
  deformation.
- `v23_cd82_paint_solver.py`: CD82 solver that decomposes target pixels into
  reversible paint primitives, then compiles strokes into keyboard/click
  actions.
- `v24_r11l_centroid_solver.py`: R11L click solver over centroid-controlled
  objects, hazard-safe intermediate states, and color-fragment carrier
  delivery.
- `v25_lp85_permutation_solver.py`: LP85 click solver over stacked button
  operators, map-cycle permutations, and goal-sprite placement.
- `v26_sb26_tape_solver.py`: SB26 keyboard/click solver over colored tape
  tokens, portal/call-stack expansion, and target-sequence placement.
- `v27_su15_particle_solver.py`: SU15 click/merge solver over numbered block
  merges, particle-hazard routing, decrement timing, and synchronized final
  placement.
- `v28_tn36_program_solver.py`: TN36 click solver that compiles target
  machine states into bit-grid opcodes and checkpoint program sequences.
- `v29_lf52_peg_solver.py`: LF52 peg/conveyor solver over two-click jumps,
  movable active landing cells, and stacked cell-state reasoning through level
  6.
- `v30_cn04_alignment_solver.py`: CN04 sprite-alignment solver over special
  pixel pairing, engine-rendered rotations, and stacked sprite variants.
- `v31_s5i5_kinematic_solver.py`: S5I5 kinematic-chain solver over
  colored resize bars, rotation buttons, and target-anchor placement through
  all eight levels.
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
python v19_ft09_constraint_solver.py --target-level 6
python v20_vc33_geometry_solver.py --target-level 7
python v21_g50t_clone_solver.py --target-level 7
python v22_re86_shape_solver.py --target-level 8
python v23_cd82_paint_solver.py --target-level 6
python v24_r11l_centroid_solver.py --target-level 6
python v25_lp85_permutation_solver.py --target-level 8
python v26_sb26_tape_solver.py --target-level 8
python v27_su15_particle_solver.py --target-level 9
python v28_tn36_program_solver.py --target-level 7
python v29_lf52_peg_solver.py --target-level 7
python v30_cn04_alignment_solver.py --target-level 6
python v31_s5i5_kinematic_solver.py --target-level 8
```

The public LS20 source currently contains 7 levels. Passing `--target-level 8`
is intentional: the runner detects that only 7 levels are available and solves
through level 7.

Outputs are written locally to:

```text
v16_signal_runner_output/target_L8/
v17_tr87_output/target_L6/
v18_wa30_output/target_L9/
v19_ft09_output/target_L6/
v20_vc33_output/target_L7/
v21_g50t_output/target_L7/
v22_re86_output/target_L8/
v23_cd82_output/target_L6/
v24_r11l_output/target_L6/
v25_lp85_output/target_L8/
v26_sb26_output/target_L8/
v27_su15_output/target_L9/
v28_tn36_output/target_L7/
v29_lf52_output/target_L7/
v30_cn04_output/target_L6/
v31_s5i5_output/target_L8/
```

These generated files are ignored by git.

## Publication Positioning

The honest claim is:

> Source-assisted symbolic/spectral planners solve public ARC-AGI-3 LS20,
> TR87, WA30, FT09, VC33, G50T, RE86, CD82, R11L, LP85, SB26, SU15, TN36, CN04,
> and S5I5 environments with 100.0 scores, and provide a concrete research path
> toward black-box interactive world-modeling agents. LF52 is partially solved
> through level 6 and is being used as a follow-up planning benchmark.

The claim to avoid is:

> This is a solved ARC-AGI-3 generalist.

The next research step is to remove source access and infer the same operator
model from frame deltas, action probes, and persistent memory.

## License

MIT for the code in this repository. ARC Prize environment files are not
vendored here and remain under their original terms.
