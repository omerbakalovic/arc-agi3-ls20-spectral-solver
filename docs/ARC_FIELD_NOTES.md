# ARC-AGI-3 Field Notes

This repository documents my attempt to solve ARC-AGI-3 public environments one by one.

The goal is not only to produce working solvers, but to understand what each environment teaches about agent design, local-world modeling, operator discovery, planning, and eventually black-box inference from frames.

I am not treating the public environments as proof of general intelligence. I am using them as a laboratory for building reusable ideas.

---

## Current Status

The current solver collection reaches 100.0 on the following public environments:

- LS20
- TR87
- WA30
- FT09
- VC33
- G50T
- RE86
- CD82
- R11L
- LP85
- SB26

These solvers are currently source-assisted / environment-specific. The next goal is to extract reusable mechanics and gradually convert them into black-box operator-induction methods.

---

## Environment Template

### Environment:

### Score:

### Core mechanic:

### What changed between frames:

### What had to be discovered:

### What is currently hardcoded:

### What could be inferred from observation:

### Reusable operator:

### Black-box potential:

### Notes:

---

## LS20

### Environment:
LS20

### Score:
100.0

### Core mechanic:
Graph/pathfinding through a local world.

### What changed between frames:
The actor moves through a structured space. Some changes are meaningful world-state changes, while some small visual changes may only represent progress or movement feedback.

### What had to be discovered:
The agent needs to distinguish meaningful actor movement from irrelevant or low-level visual changes. It also needs to identify reachable areas, obstacles, interactive objects, and goal structure.

### What is currently hardcoded:
The current solution relies on environment-specific knowledge and source/cache-assisted structure.

### What could be inferred from observation:
Actor position, legal moves, wall collisions, reachable graph, and interactive targets could potentially be inferred from action-frame deltas.

### Reusable operator:
Movement model + map extraction + pathfinding.

### Black-box potential:
High. This environment is a good candidate for moving from source-assisted solving toward observation-based operator induction.

### Notes:
LS20 is important because it teaches the basic pattern: ignore micro-noise, track macro-state, infer movement rules, then plan.
