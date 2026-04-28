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

## VC33

Command:

```bash
python v20_vc33_geometry_solver.py --target-level 7
```

Environment:

```text
game: vc33
environment id: vc33-5430563c
available levels: 7
requested target: 7
effective target: 7
```

Final scorecard:

```text
score: 100.0
levels_completed: 7 / 7
completed: true
state: WIN
total_actions: 217
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 3 | 7 | 100.0 |
| 2 | 7 | 18 | 100.0 |
| 3 | 23 | 44 | 100.0 |
| 4 | 21 | 61 | 100.0 |
| 5 | 68 | 131 | 100.0 |
| 6 | 20 | 34 | 100.0 |
| 7 | 75 | 152 | 100.0 |

Generated macro-click plans:

```text
L1: [1, 1, 1]
L2: [1, 1, 3, 3, 3, 3, 3]
L3: [0, 2, 0, 2, 0, 4, 2, 0, 4, 2, 0, 4, 2, 0, 6, 6, 6, 6, 6, 6, 6, 6, 6]
L4: [3, 3, 1, 3, 3, 3, 4, 4, 6, 4, 0, 6, 4, 6, 4, 6, 4, 6, 4, 6, 4]
L5: [8, 8, 5, 5, 2, 5, 2, 5, 2, 5, 7, 3, 0, 3, 3, 3, 3, 4, 2, 2, 2, 2, 2, 2, 5, 5, 1, 3, 3, 3, 3, 3, 0, 3, 0, 6, 3, 0, 6, 3, 0, 0, 0, 5, 8, 5, 8, 5, 5, 5, 5, 4, 5, 5, 5, 5, 2, 5, 7, 8, 8, 8, 8, 8, 8, 8, 3, 0]
L6: [0, 1, 1, 1, 2, 4, 4, 5, 5, 5, 5, 5, 5, 3, 1, 1, 1, 1, 1, 1]
L7: [3, 6, 4, 6, 6, 6, 7, 7, 7, 7, 7, 1, 1, 1, 1, 1, 1, 5, 5, 5, 9, 8, 8, 8, 1, 1, 1, 10, 5, 5, 5, 5, 5, 5, 0, 0, 0, 0, 0, 4, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 6, 10, 5, 3, 3, 3, 3, 0, 0, 0, 0, 0, 0, 4, 1, 3, 1, 3, 1, 3, 1, 3, 1, 3, 1]
```

Notes:

- VC33 is solved as a one-dimensional platform transport system.
- Small click sprites transfer platform mass between neighboring columns.
- Bridge sprites swap markers between aligned platforms while preserving the
  marker's progress coordinate.
- Level 7 was found by a lightweight exact macro-state search over platform
  heights, marker locations, and bridge readiness, then replayed on the real
  ARC runtime.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## G50T

Command:

```bash
python v21_g50t_clone_solver.py --target-level 7
```

Environment:

```text
game: g50t
environment id: g50t-5849a774
available levels: 7
requested target: 7
effective target: 7
```

Final scorecard:

```text
score: 100.0
levels_completed: 7 / 7
completed: true
state: WIN
total_actions: 309
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 17 | 78 | 100.0 |
| 2 | 31 | 175 | 100.0 |
| 3 | 64 | 179 | 100.0 |
| 4 | 31 | 230 | 100.0 |
| 5 | 50 | 96 | 100.0 |
| 6 | 49 | 54 | 100.0 |
| 7 | 67 | 67 | 100.0 |

Generated keyboard plans:

```text
L1: RRRRADDDDDDDRRRRR
L2: LLADDDDLLLLUULLAUUULLLLLLLDDRRR
L3: UURRRRDDDDRAUURRRRRRRDDDDDDDLLLLLAUURRRRRRRDDDDDDDLLLLLLLUUURRUU
L4: DDRDADDRRUURRDDDALLLDDDDDRRRLLL
L5: UDDRRRDDDADRRRUURRRDDDRRRADRRRUURRRDDDDDRLDLLLLLUU
L6: LLUALLULLALLDLLLLUULLLDDDDDRRUDLLUUUUURRRDDRRDDRR
L7: DDLRUULLUUADDRRUUUURRDDDDUUUULLLUURRRADDRRUUUURRDDDDUDUDUDUDUDUDLLL
```

Notes:

- G50T is a keyboard puzzle centered on ACTION5 rewind/clone semantics.
- Rewound movement histories become clone tracks; later moves advance the live
  player, clones, and autonomous actors in synchronized time.
- Levels 1-3 use clone-held pressure gates and timed moving-door passages.
- Levels 4-5 add paired swap pads driven by pressure triggers.
- Levels 6-7 use clone-opened corridors to steer autonomous actors onto
  switches, then combine actor-triggered swaps with final player routing.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## RE86

Command:

```bash
python v22_re86_shape_solver.py --target-level 8
```

Environment:

```text
game: re86
environment id: re86-8af5384d
available levels: 8
requested target: 8
effective target: 8
```

Final scorecard:

```text
score: 100.0
levels_completed: 8 / 8
completed: true
state: WIN
total_actions: 507
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 20 | 26 | 100.0 |
| 2 | 36 | 42 | 100.0 |
| 3 | 47 | 86 | 100.0 |
| 4 | 42 | 108 | 100.0 |
| 5 | 63 | 189 | 100.0 |
| 6 | 46 | 139 | 100.0 |
| 7 | 98 | 424 | 100.0 |
| 8 | 155 | 241 | 100.0 |

Generated keyboard plans:

```text
L1: RRRRUUUUUUUALLUUUUUU
L2: LLLDDDDDDDDDDALLLLLLUUUUUUALLLLLLLDD
L3: LUUUUUUUUUUUUUARRRRRRRRUUUUUUUUALLLLLLLLLUUUUUU
L4: UUUUULLLLLLLDDDLLLLLLADDDDDDDDRRRRRRUUUUUL
L5: ULLDRUUUUUUUUURRRADDDDDDDDDDRRRRRRRUUUUADDDDDDDLLLLLLLLLLLURRRR
L6: UURRDRDRRRRRRRULRRRADDDDDLLULDDUUUUUULLLLLLLLL
L7: UUUURRRUUULUUUURRRDRRRRRRDDDDDDDAUUUUUUUUUUUUURDDDDDURRRRRRRRAUUUUUURRRRLLLLLLLLLUUURDUUUUUUURRDDD
L8: LLLDDDUUUUUUUUUUULLLLLLLURRRRRRRRUUUURRRDRRDRRDDLLLDDDDDDDDDLLLDDDDLLLLLLLLAUUUUUUUUUUUUUUDLLLLLLLLLLLLDDRRRRRRRRRUUUURRRDRRDRRDDLLLDDDDDDDDDLLLDLLLDLLLLLL
```

Notes:

- RE86 is solved as a sparse target-composition problem over movable sprite
  masks.
- Levels 1-3 are direct geometric overlay plans.
- Levels 4-5 add color-pad transport and recoloring.
- Levels 6-8 add obstacle-driven deformation: special rectangles resize, and
  cross sprites shift their full row or column through collision operators.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## CD82

Command:

```bash
python v23_cd82_paint_solver.py --target-level 6
```

Environment:

```text
game: cd82
environment id: cd82-fb555c5d
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
total_actions: 70
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 5 | 55 | 100.0 |
| 2 | 6 | 8 | 100.0 |
| 3 | 16 | 41 | 100.0 |
| 4 | 14 | 21 | 100.0 |
| 5 | 13 | 23 | 100.0 |
| 6 | 16 | 23 | 100.0 |

Generated keyboard/click plans:

```text
L1: URRDP
L2: P[C12]DRRP
L3: [C8]DRRP[C14]LP[C15]LUUP[C12]DA
L4: [C12]P[C15]DRRP[C9]UULP[C11]A
L5: [C9]P[C8]A[C14]URRP[C12]DDP
L6: [C14]DRP[C8]LUUP[C11]RA[C15]LDA
```

Notes:

- CD82 is solved as a 10x10 target-painting signal.
- The solver reverse-peels the target into uniform paint primitives: basket
  half-planes and arrow strip strokes.
- The resulting strokes are compiled into color selections, brush movement,
  and paint actions, then replayed against the real ARC runtime.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## R11L

Command:

```bash
python v24_r11l_centroid_solver.py --target-level 6
```

Environment:

```text
game: r11l
environment id: r11l-495a7899
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
total_actions: 73
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 4 | 22 | 100.0 |
| 2 | 9 | 33 | 100.0 |
| 3 | 11 | 51 | 100.0 |
| 4 | 14 | 26 | 100.0 |
| 5 | 17 | 52 | 100.0 |
| 6 | 18 | 49 | 100.0 |

Notes:

- R11L is solved as a centroid-control problem: small clickable points define
  the position of a larger object.
- The solver searches over safe intermediate centroid states, so paths avoid
  hazard masks after every individual control-point move.
- Levels 5-6 use blank carrier objects that collect colored fragments, match
  target color sets, and then move to the target zones.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## LP85

Command:

```bash
python v25_lp85_permutation_solver.py --target-level 8
```

Environment:

```text
game: lp85
environment id: lp85-305b61c3
available levels: 8
requested target: 8
effective target: 8
```

Final scorecard:

```text
score: 100.0
levels_completed: 8 / 8
completed: true
state: WIN
total_actions: 79
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 5 | 17 | 100.0 |
| 2 | 8 | 38 | 100.0 |
| 3 | 16 | 31 | 100.0 |
| 4 | 12 | 16 | 100.0 |
| 5 | 9 | 41 | 100.0 |
| 6 | 19 | 60 | 100.0 |
| 7 | 5 | 26 | 100.0 |
| 8 | 5 | 159 | 100.0 |

Generated click/operator plans:

```text
L1: AL AL AL AL AL
L2: AR CR CR CR AR AR AR CR
L3: AL AL AL AL BL BL BL BL AL BL AL AL AL AL AL BL
L4: BL BL BL BL AL AL AL AL AL AL AL AL
L5: AR AR BR AL BL AL AL AL AL
L6: 13R+11R+9R+16R+10R+12R+14R+15R 13R+11R+9R+16R+10R+12R+14R+15R 8R+3R+1R+4R+5R+2R+6R+7R 8R+3R+1R+4R+5R+2R+6R+7R BR+CR+AR BR+CR+AR 23R+18R+24R+22R+17R+20R+19R+21R 23R+18R+24R+22R+17R+20R+19R+21R IR+GR+HR IR+GR+HR IR+GR+HR IR+GR+HR IR+GR+HR IR+GR+HR DR+ER+FR DR+ER+FR DR+ER+FR DR+ER+FR 27R+25R+26R
L7: DR+AR BL AL+DL BR AL+DL
L8: DR+ER+FR AL BR CR EL+DL+FL
```

Notes:

- LP85 is solved as a finite permutation system over movable goal sprites.
- Each click may represent a stacked macro-button: the runtime applies every
  overlapping `button_*` operator in source order.
- The solver searches the induced state space of `goal` and `goal-o` sprite
  positions, then replays the click coordinates against the real ARC runtime.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## SB26

Command:

```bash
python v26_sb26_tape_solver.py --target-level 8
```

Environment:

```text
game: sb26
environment id: sb26-7fbdac44
available levels: 8
requested target: 8
effective target: 8
```

Final scorecard:

```text
score: 100.0
levels_completed: 8 / 8
completed: true
state: WIN
total_actions: 124
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 9 | 18 | 100.0 |
| 2 | 15 | 28 | 100.0 |
| 3 | 15 | 18 | 100.0 |
| 4 | 15 | 19 | 100.0 |
| 5 | 17 | 31 | 100.0 |
| 6 | 19 | 23 | 100.0 |
| 7 | 17 | 58 | 100.0 |
| 8 | 17 | 18 | 100.0 |

Generated tape placements:

```text
L1: T9@(20,27) T14@(26,27) T11@(32,27) T15@(38,27)
L2: T12@(20,20) T15@(26,20) T6@(38,20) T8@(20,34) T9@(26,34) T14@(32,34) T11@(38,34)
L3: T8@(17,21) T11@(29,21) T12@(41,21) T14@(17,33) T15@(23,33) T6@(35,33) T9@(41,33)
L4: T11@(17,20) T8@(23,20) P14@(29,20) T12@(35,20) T15@(41,20) T9@(29,34) T6@(35,34)
L5: T6@(17,20) P9@(23,20) P9@(29,20) T11@(35,20) T15@(41,20) T14@(23,34) T8@(29,34) T8@(35,34)
L6: P9@(10,20) P12@(16,20) P14@(22,20) T6@(42,20) T6@(48,20) T11@(16,34) T11@(22,34) T15@(42,34) T15@(48,34)
L7: T8@(23,14) T9@(29,14) P9@(35,14) P14@(23,27) T9@(29,27) T8@(35,27) T14@(23,40) T14@(35,40)
L8: T8@(20,24) T11@(26,24) T12@(32,24) P9@(38,24) T9@(20,38) T14@(26,38) T15@(32,38) P8@(38,38)
```

Notes:

- SB26 is solved as a small tape language: tile tokens emit colors, portal
  tokens call another frame, and the root frame must emit the target row.
- The solver backtracks over token placements and validates the resulting
  call-stack expansion before replay.
- Each placement is compiled into two clicks, followed by one `ACTION5` to run
  the tape verifier.
- Like the other runners, this is source-assisted and not yet a black-box
  ARC-AGI-3 agent.

## SU15

Command:

```bash
python v27_su15_particle_solver.py --target-level 4
```

Environment:

```text
game: su15
environment id: su15-1944f8ab
available levels: 9
requested target: 4
effective target: 4
```

Final scorecard:

```text
score: 22.22222222222222
levels_completed: 4 / 9
completed: false
state: NOT_FINISHED
total_actions: 49
resets: 0
```

Per-level actions:

| Level | Actions | Baseline actions | Level score |
|---:|---:|---:|---:|
| 1 | 8 | 22 | 100.0 |
| 2 | 12 | 42 | 100.0 |
| 3 | 17 | 26 | 100.0 |
| 4 | 12 | 115 | 100.0 |
| 5 | 0 | 36 | 0.0 |
| 6 | 0 | 31 | 0.0 |
| 7 | 0 | 8 | 0.0 |
| 8 | 0 | 40 | 0.0 |
| 9 | 0 | 41 | 0.0 |

Generated click plans:

```text
L1: (4,50) (8,42) (12,34) (16,26) (20,18) (28,14) (36,14) (44,14)
L2: (16,54) (48,54) (24,54) (32,54) (40,54) (16,38) (40,38) (24,38) (32,38) (36,46) (32,38) (32,30)
L3: (60,22) (32,18) (12,26) (20,18) (16,22) (32,26) (24,22) (52,22) (48,26) (44,34) (36,38) (28,42) (20,46) (12,50) (24,30) (24,38) (24,46)
L4: (32,30) (32,46) (32,38) (48,30) (8,26) (8,42) (8,34) (24,38) (16,36) (12,44) (8,52) (8,56)
```

Notes:

- SU15 is a click merge puzzle: equal numbered blocks merge into the next
  value when selected and overlapped by a click.
- Level 4 introduces the first particle hazard.  The plan pushes the particle
  away long enough to build and place the required level-3 block.
- Level 5 remains the next open frontier: particles can decrement both
  intermediate level-2 blocks before they merge, so the solver needs a more
  explicit particle-control or compensation planner.
