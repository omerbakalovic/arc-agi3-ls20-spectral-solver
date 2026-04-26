# Reproduction Results

Date: 2026-04-26

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
python v18_wa30_object_solver.py --target-level 3
```

Environment:

```text
game: wa30
environment id: wa30-ee6fef47
available levels: 9
requested target: 3
effective target: 3
```

Final scorecard:

```text
score: 13.333333333333334
levels_completed: 3 / 9
completed: false
state: NOT_FINISHED
total_actions: 163
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 26 | 71 | 100.0 |
| 2 | 61 | 119 | 100.0 |
| 3 | 76 | 183 | 100.0 |
| 4 | 0 | 98 | 0.0 |
| 5 | 0 | 368 | 0.0 |
| 6 | 0 | 68 | 0.0 |
| 7 | 0 | 79 | 0.0 |
| 8 | 0 | 442 | 0.0 |
| 9 | 0 | 415 | 0.0 |

Generated player plans:

```text
L1: UUGUULGLULGURRRRDGRRUGDLLG
L2: DDDDDDDDRRRRRRRGLLLLLLULGUUURRRRRRRRGLLLLLLLLLDDG
L3: UUUURGRRRGLLLLLLURGRRRRRRGDDDDDDLLLLLDRGRRRRRG
```

Notes:

- Level 1 is solved by an exact source-assisted grab/drag planner over player,
  boxes, facing, and held-object state.
- Level 2 is solved by a player/helper cooperative plan: the player clears two
  far boxes while the helper solves the nearest boxes.
- Level 3 is solved by a hazard-column handoff: the player moves left-side
  boxes to the `x=32` barrier, and the helper carries them to the target zone.
- Level 4 is not solved yet; idle-helper rollout stalls after one outer box,
  so the next step is a multi-helper interior-ring planner.
