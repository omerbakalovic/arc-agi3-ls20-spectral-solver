# Reproduction Results

Date: 2026-04-27

## LS20

Command:

```bash
python v16_signal_runner.py --target-level 8
```

Environment:

```text
game: ls20
environment id: ls20-9607627b
available levels: 7
requested target: 8
effective target: 7
```

Final scorecard:

```text
score: 100.0
levels_completed: 7 / 7
completed: true
state: WIN
total_actions: 334
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 16 | 22 | 100.0 |
| 2 | 46 | 123 | 100.0 |
| 3 | 42 | 73 | 100.0 |
| 4 | 52 | 84 | 100.0 |
| 5 | 48 | 96 | 100.0 |
| 6 | 75 | 192 | 100.0 |
| 7 | 55 | 186 | 100.0 |

Generated plans for levels 3-7:

```text
L3: UUUUUURLDDRDDDLDDDUUULLURRRRRRRUUULUDURDD
L4: LLLDDDLRDDLLULDUDUDURUDDLLLLDLDDDLRUDDLRUUUURURUULLL
L5: ULUULULDLRLRLRRURLDDLLLULUDDDDLDDRRLDDRDRRRRRRRUU
L6: ULULLUUURRRRRRUURRUUDRDDUULULDDDDLLDULLDLLUUUUUDRRDULLUUURRRRRRDRRUUDRDDDDD
L7: UUDDLLDDDDDUDRDURUDUDUDUDLLUUURRRRURRDURRUURDDLLLULDDDD
```

Notes:

- Levels 1 and 2 currently use bootstrap routes.
- Levels 3-7 are planned from parsed LS20 level definitions.
- This demonstrates a working solver for a public environment, not a
  competition-ready black-box generalist.

## TR87

Command:

```bash
python v17_tr87_symbolic_solver.py --target-level 6
```

Environment:

```text
game: tr87
environment id: tr87-cd924810
available levels: 6
requested target: 6
effective target: 6
```

Final scorecard:

```text
score: 100.0
levels_completed: 6 / 6
completed: true
state: WIN
total_actions: 118
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 14 | 54 | 100.0 |
| 2 | 25 | 58 | 100.0 |
| 3 | 21 | 40 | 100.0 |
| 4 | 21 | 45 | 100.0 |
| 5 | 14 | 71 | 100.0 |
| 6 | 23 | 146 | 100.0 |

Generated plans:

```text
L1: DDRDDRUUURDRDD
L2: DDDRDDRUUURUURUUURUUURDDD
L3: DRDDRDDDRDDRUUURDDRDD
L4: UUURUUURUUURRDDRUUURD
L5: RDRURURDRUURRD
L6: UULUUURRURDRURRDDRUURRD
```

Notes:

- TR87 is a symbolic transduction puzzle rather than a spatial maze.
- Levels 1-4 solve target rows under fixed rewrite rules.
- Level 5 solves modulo-7 constraints over mutable rewrite rules.
- Level 6 solves mutable tree-translation constraints.
- Like LS20, this is source-assisted and not yet a black-box ARC-AGI-3 agent.

## WA30

Command:

```bash
python v18_wa30_object_solver.py --target-level 9
```

Environment:

```text
game: wa30
environment id: wa30-ee6fef47
available levels: 9
requested target: 9
effective target: 9
```

Final scorecard:

```text
score: 100.0
levels_completed: 9 / 9
completed: true
state: WIN
total_actions: 616
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 26 | 71 | 100.0 |
| 2 | 61 | 119 | 100.0 |
| 3 | 76 | 183 | 100.0 |
| 4 | 47 | 98 | 100.0 |
| 5 | 117 | 368 | 100.0 |
| 6 | 50 | 68 | 100.0 |
| 7 | 36 | 79 | 100.0 |
| 8 | 143 | 442 | 100.0 |
| 9 | 60 | 415 | 100.0 |

Generated player plans:

```text
L1: UUGUULGLULGURRRRDGRRUGDLLG
L2: DDDDDDDDRRRRRRRGLLLLLLULGUUURRRRRRRRGLLLLLLLLLDDG
L3: UUUURGRRRGLLLLLLURGRRRRRRGDDDDDDLLLLLDRGRRRRRG
L4: UULGLGRGDRRGUGUGDDDGDGLLGLGUURRDGDDG
L5: DDDDRRRGUUUUULLLLLLLLLLLLLGUURRDRRRRRRUUUUUURGDDDDDLDLLLLLLULLGDRRRRRRUUUUURRRGDDDDDDLLLLLLLLLLDLLG
L6: UUUUUUURRRRRRRRDRGRGLLLUULLGDDRRRRRRDRGULLLLULLLUG
L7: GGURRRRRRRGDGLLLLLLLLLGURRRRGLLLLLDG
L8: RRRUUUUUGGDDDDDRRRRRDDDDDLDUGDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDUUUUURUUULLLLUUUUULLGRRRRRRRURRRRDGDGRRRRRRGDDDDGULGDU
L9: RRRRRGUUGLLUGUUGDDDRGRUGDDLLLLLLLLLLGRUUGDLGRRRRRURUUGDLGLDG
```

Notes:

- Level 1 is solved by an exact source-assisted grab/drag planner over player,
  boxes, facing, and held-object state.
- Level 2 is solved by a player/helper cooperative plan: the player clears two
  far boxes while the helper solves the nearest boxes.
- Level 3 is solved by a hazard-column handoff: the player moves left-side
  boxes to the `x=32` barrier, and the helper carries them to the target zone.
- Levels 4-5 extend the helper handoff idea to multi-helper and staged
  far-box layouts.
- Levels 6-8 use special-object removal/staging and helper deadlock release.
- Level 9 uses final transport orchestration: the player moves right-side boxes
  into the left target bank while helpers and the special object finish staging.

## FT09

Command:

```bash
python v19_ft09_constraint_solver.py --target-level 6
```

Environment:

```text
game: ft09
environment id: ft09-0d8bbf25
available levels: 6
requested target: 6
effective target: 6
```

Final scorecard:

```text
score: 100.0
levels_completed: 6 / 6
completed: true
state: WIN
total_actions: 75
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 4 | 43 | 100.0 |
| 2 | 7 | 12 | 100.0 |
| 3 | 14 | 23 | 100.0 |
| 4 | 16 | 28 | 100.0 |
| 5 | 21 | 65 | 100.0 |
| 6 | 13 | 37 | 100.0 |

Generated click plans:

```text
L1: (18,18), (18,22), (26,22), (18,26)
L2: (10,7), (10,11), (18,11), (10,15), (18,15), (10,23), (14,23)
L3: (10,2), (14,2), (18,2), (10,6), (6,10), (14,10), (6,14), (22,14), (14,18), (22,18), (10,22), (10,26), (14,26), (18,26)
L4: (10,7)x2, (14,7), (22,7), (14,11), (22,11), (10,15)x2, (14,15), (18,15), (10,23)x2, (14,23)x2, (18,23)x2
L5: (11,2), (15,2), (7,6), (11,6), (15,6), (7,10), (15,10), (23,10), (7,14), (11,14), (15,14), (7,18), (15,18), (19,18), (23,18), (15,22), (19,22), (23,22), (7,26), (15,26), (19,26)
L6: (2,3), (2,7), (10,7), (18,7), (6,11), (10,11), (6,15), (14,15), (18,15), (22,15), (10,19), (22,19), (26,19)
```

Notes:

- FT09 is solved as a modulo-color click constraint system.
- `Hkx` sprites use the level click kernel; `NTi` sprites use center plus
  marked `6` offsets.
- Binary-palette levels are solved by GF(2) elimination.
- The three-color center-only level is solved by choosing allowed values with
  minimal modulo clicks.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.
