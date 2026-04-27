# ARC-AGI-3 Field Notes

This document is not a reproduction log.  
Reproduction results, scores, commands, action counts and generated plans are documented in `docs/RESULTS.md`.

This document is a research diary: what each solved public environment teaches about agent design, operator discovery, planning, and the transition from source-assisted solving toward black-box inference from frames.

The current solvers are not presented as a competition-ready general ARC-AGI-3 agent. They are treated as laboratories for extracting reusable mechanisms.

---

## How to Read These Notes

For each environment, I describe:

- the core mechanic
- what the current solver exploits
- what a black-box agent would need to infer
- the reusable operator behind the solution
- why the environment matters for future generalization

---

## LS20 — Movement, Map Extraction, Pathfinding

### Core lesson

LS20 teaches the basic local-world loop:

1. identify the actor
2. distinguish real movement from irrelevant visual noise
3. infer walls and walkable regions
4. build a graph
5. plan a route

### Current limitation

The existing solver is source-assisted. It can use parsed level structure instead of discovering everything from interaction.

### Black-box direction

A black-box version should infer:

- actor position from frame deltas
- legal moves from action attempts
- collision behavior
- reachable space
- interactive targets
- goal condition

### Reusable operator

Movement model + graph extraction + pathfinding.

### Why it matters

This is the foundation for many other ARC-AGI-3 environments. Before solving symbolic or object-heavy worlds, the agent must first learn how to exist inside a local world.

---

## TR87 — Symbolic Transduction

### Core lesson

TR87 is not mainly about space. It is about discovering symbolic rewrite rules.

### Current limitation

The current solver has access to source-backed symbolic state.

### Black-box direction

A black-box version should infer:

- which visible symbols are mutable
- which actions transform symbols
- whether transformations are deterministic
- whether the problem is a rewrite system, modulo system, or tree translation problem

### Reusable operator

Symbolic rule induction + constraint solving.

### Why it matters

TR87 shows that ARC-AGI-3 is not only navigation. Some environments require the agent to infer an abstract machine behind the pixels.

---

## FT09 — Click Kernels and Modular Constraints

### Core lesson

FT09 teaches that a click is not just a click. A click can be an operator with a local effect kernel.

### Current limitation

The current solver knows the click kernel from source-assisted structure.

### Black-box direction

A black-box version should probe clicks, observe affected cells, and reconstruct the kernel from frame deltas.

### Reusable operator

Action-effect probing + modular linear solving.

### Why it matters

This is one of the clearest bridges from source-assisted solving to black-box induction. The agent can experimentally discover the rules.

---

## WA30 — Object Transport and Cooperation

### Core lesson

WA30 teaches object manipulation, helper behavior, staging, handoff, and deadlock avoidance.

### Current limitation

The current solver uses detailed environment-specific knowledge about players, helpers, boxes, facing direction, held objects and special object behavior.

### Black-box direction

A black-box version should infer:

- which objects are movable
- which actors can move them
- when an object is held
- when helper behavior is autonomous
- which layouts create deadlocks
- how to stage objects before final delivery

### Reusable operator

Grab/drag/transport + helper coordination.

### Why it matters

This is closer to real agent planning than simple pathfinding. The agent must reason about other entities, not just itself.

---

## VC33 — Geometry Transport

### Core lesson

VC33 teaches macro-state planning over geometry. The visible scene encodes a smaller abstract transport system.

### Current limitation

The current solver uses source-assisted understanding of platform mass, marker movement and bridge behavior.

### Black-box direction

A black-box version should infer:

- clickable geometric components
- conserved quantities
- neighboring-column transfers
- bridge/swap rules
- marker progress state

### Reusable operator

Geometric state abstraction + macro-state search.

### Why it matters

VC33 is important because it shows that the true state can be much smaller than the pixels.

---

## G50T — Rewind, Clones and Time Tracks

### Core lesson

G50T teaches temporal mechanics: previous movement histories can become future actors.

### Current limitation

The current solver understands ACTION5 rewind/clone behavior from environment-specific analysis.

### Black-box direction

A black-box version should infer:

- that one action creates a clone/history object
- that clones replay previous movement
- that time-synchronized entities can hold gates or trigger swaps
- that planning must include future effects of past actions

### Reusable operator

Temporal replay / clone-track planning.

### Why it matters

This environment is a strong test of whether an agent can infer non-obvious causal structure.

---

## RE86 — Shape Composition and Deformation

### Core lesson

RE86 teaches that objects are not only points. They can be masks, shapes, overlays, recolored objects, or deformable structures.

### Current limitation

The current solver relies on source-assisted knowledge of sprite masks and transformation behavior.

### Black-box direction

A black-box version should infer:

- movable masks
- target composition
- recoloring pads
- deformation through collisions
- row/column shifting operators

### Reusable operator

Shape-mask transport + composition planning.

### Why it matters

This connects ARC-AGI-3 back to classical ARC-style abstraction: shapes, colors, overlays and transformations.

---

## CD82 — Painting Primitives

### Core lesson

CD82 teaches reverse construction: infer which primitive strokes could have produced a target image.

### Current limitation

The current solver knows the paint primitives and compiles target decomposition into actions.

### Black-box direction

A black-box version should infer:

- brush position
- selected color
- paint action semantics
- primitive stroke shapes
- how target images decompose into valid strokes

### Reusable operator

Target decomposition + primitive program synthesis.

### Why it matters

This is close to program synthesis: the agent must explain an image as a sequence of operations.

---

## R11L — Centroid Control

### Core lesson

R11L teaches indirect control. The agent does not directly move the large object; it moves control points that define its centroid.

### Current limitation

The current solver uses source-assisted knowledge of control-point effects and hazard masks.

### Black-box direction

A black-box version should infer:

- which points control which object
- how object position depends on point positions
- safe intermediate states
- hazard constraints after every small movement

### Reusable operator

Indirect control + safe-state planning.

### Why it matters

This is valuable because many agent problems require controlling a system through hidden variables, not direct movement.

---

## LP85 — Permutations and Macro Buttons

### Core lesson

LP85 teaches finite-state permutation systems. A click may trigger one or more stacked operators.

### Current limitation

The current solver knows overlapping button behavior and source order.

### Black-box direction

A black-box version should infer:

- which clicks are buttons
- which objects are permuted
- whether multiple operators fire from one click
- how to search the finite permutation state space

### Reusable operator

Permutation induction + finite-state search.

### Why it matters

This is a clean example of reducing a visual environment into an abstract algebraic system.

---

## SB26 — Tape Language and Call Stack

### Core lesson

SB26 teaches that an environment can implement a tiny programming language.

### Current limitation

The current solver knows token semantics and validates call-stack expansion.

### Black-box direction

A black-box version should infer:

- token placement rules
- token output semantics
- portal/call behavior
- frame expansion
- target row generation

### Reusable operator

Tiny-language induction + program search.

### Why it matters

SB26 is one of the strongest examples that ARC-AGI-3 environments may hide interpreters, grammars or machines behind simple visuals.

---

## Emerging Operator Library

Across the solved public environments, the following reusable operator families appear:

| Operator family | Example environments |
|---|---|
| Movement and pathfinding | LS20 |
| Symbolic rewrite rules | TR87 |
| Object transport | WA30 |
| Click-effect kernels | FT09 |
| Geometric macro-state planning | VC33 |
| Temporal clone/replay mechanics | G50T |
| Shape composition | RE86 |
| Paint primitive synthesis | CD82 |
| Indirect centroid control | R11L |
| Permutation systems | LP85 |
| Tape/program interpretation | SB26 |

---

## Main Research Direction

The next step is not only to solve more public environments.

The next step is to convert each solved environment into a question:

> What would an agent have to observe, test and infer in order to discover this mechanic without source access?

That is the bridge from environment-specific solvers toward a real ARC-AGI-3 agent.
