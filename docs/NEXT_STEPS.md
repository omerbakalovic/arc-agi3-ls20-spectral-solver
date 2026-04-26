# Next Steps Toward a Real ARC-AGI-3 Agent

## 1. Remove Source Introspection

Current limitation:

```text
v15_level3_signal_planner.py reads environment_files/ls20/9607627b/ls20.py
```

Goal:

Infer the same model from interaction:

- detect walkable regions from frames
- identify objects and persistent sprite-like components
- probe actions near candidate objects
- classify observed frame deltas as shape/color/rotation/teleport/energy events
- build the operator graph from evidence rather than source code

## 2. Convert to the Official Agent Interface

The current runner directly controls `arc.make("ls20")`.

Goal:

Wrap the planner as an ARC-AGI-3 agent class compatible with the public agents
repo interface.

## 3. Test Beyond LS20

Minimum next games:

- `vc33`
- `ft09`

This will tell us which parts are truly general:

- grid/floor perception
- object-effect inference
- multi-step planning
- goal acquisition
- memory across attempts

## 4. Keep the Math Core

The promising parts worth preserving:

- graph Laplacian features
- Fiedler/topology diagnostics
- frame-delta event classification
- staged planning over typed operators
- persistent danger/progress memory

