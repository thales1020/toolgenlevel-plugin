---
name: Tile Explorer game rules & solver bugs
description: Non-obvious game rules and solver pitfalls that bit me during level-design work
type: project
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Tile label display is internal_id + 1 (off-by-one).** The JSON/solver uses 0-indexed tile_ids (0-11 for 12 types). The play UI shows them as 1-indexed labels (1-12). When showing a solution path to the user, always map `display_label = tile_id + 1`. I hit this when the user said "I see tile 10, 4, 7, 7, 8" but my JSON had [9, 3, 6, 6, 7] — they're the same, offset by 1.

**For SHIPPING art, `i` must be a real Group_1 art id — the ids are NOT free-form.** Generated levels
default to sequential tile_ids (0,1,2,…), which look fine analytically but have no matching sprite in
the real game. The 30 valid ship ids are `VALID_GROUP1_IDS = [85] + list(range(142, 171))`
(`gen_pattern.py`). `gen_pattern.py` remaps onto these by default (bijective — no difficulty/
solvability change); pass `--raw-ids` only if you deliberately want the raw `tile_id+1` sequence
instead (e.g. for a solver-debug artifact, never for a level meant to actually load in-game).

**Bonus (1001) collides as a CIRCLE, not a box — mission/normal use a box.** Any overlap check
involving a bonus tile must use `dx**2 + dy**2 < (ha+hb)**2` (corners excluded); mission (1002) and
normal↔normal pairs use the AABB box `|dx|<ha+hb AND |dy|<ha+hb`. Must stay consistent across
`solve_special._build_visibility_2x2`, `make_play_html.overlaps()`, and `reserve_special`'s placement
gates — treating bonus as a box over-covers its corners, wrongly hides the start triple underneath,
and produces a false "unsolvable" verdict. Half-extents: 2×2 stack → 1.0, 3×3 stack → 1.5, normal →
0.5. (0.7.2 — collision shape was wrong before that.)

**Win = board empty, NOT tray empty — there is no ÷3 requirement for solvability.** Confirmed directly
against `tile_level_simulator.py`'s `PlayWindow._pick_tile`: `if not self.active: self.won = True`,
checked BEFORE the game-over/lose check. A tile type whose count isn't a multiple of 3 just leaves 1-2
unmatched tiles stuck in the tray forever once picked — that's still a WIN as long as the tray never
hits `TRAY_SIZE` with no available triple along the way. 0.9.0 shipped a `solve_v3` guard that raised
`ValueError` on any board with `total_cells % 3 != 0` and no specials, reasoning "can never fully
clear" — that reasoning was wrong, and the guard incorrectly rejected real winnable boards (caught via
a real shipped level: 77 cells, one type at 8 copies, genuinely solvable). Reverted in 0.9.5. `%3==0`
per type is a generator DESIGN CONVENTION (`gen_pattern.py`/`reserve_special.py` use it by default for
clean, no-leftover distributions) — never reintroduce it as a solver-level correctness guard; if a
board's solvability is in question, run `solve_v3`/`solve_any`, don't precompute an answer from ÷3.

**Tray game-over rule is `size >= 7 AND no triple`, NOT `size > 7`.** From `tile_level_simulator.py:2721-2728` (`PlayWindow._on_click`): after insert + auto-clear, if tray length ≥ 7 with no count ≥ 3, game over fires. My first beam/DFS solvers used `> TRAY_SIZE` (overflow check) which allowed tray=7 states and produced "valid solutions" that instantly lose in the real game. Fix: `(tsize + 1) >= TRAY_SIZE` skip.

**Atomic triple optimization in DFS must bounds-check intermediate tray size.** When doing a "pick 3 of same type" atomic action, intermediate state between pick 1 and pick 3 has tray size `cur_tsize + (needed-1)` before the clear fires. That intermediate must be `< TRAY_SIZE`. I originally only checked the final size, which let invalid solutions through.

**Shuffle booster has been modified to guarantee an immediate triple after use.** The stock `_use_shuffle` did a plain `random.shuffle` of active tile IDs across cells. The custom version (see `tile_level_simulator.py:2764`) picks the remaining type with the most copies (≥3 required), force-places 3 of that type on random pickable cells, then shuffles the rest. Fallback: if no type has ≥3 copies OR < 3 pickable cells, plain random shuffle.

**v3 solvers do NOT model buffs.** `verify_smart_v3`, `solve_path`, and `count_solutions` all solve the level with tray=7 hard ceiling and no Shuffle/Undo/+1Slot. A level flagged "unsolvable" by v3 may still be beatable in-game via buffs — treat "v3 unsolvable" and "unwinnable" as different bars.

**Geometry must never drift silently during tile assignment.** `gen_pattern.py::_load_trimmed` and
`reserve_special.py::_gen_normal_level` used to silently drop up to 2 cells when a layout wasn't ÷3,
still claiming the original layout's name — a "Layout_A silently becomes Layout_A1" bug. Both now
hard-fail by default (opt in with `--allow-trim`, which records the trim and renames the output).
See `SKILL.md §22b`.

**Why:** These are all one-slot-off / one-rule-off bugs that look correct until you actually replay the solution in the game UI. Each one wasted multiple iterations to track down.

**How to apply:** Any new solver or replay script I write MUST use `>= TRAY_SIZE AND no triple` as the game-over check, and any atomic/batch action must validate intermediate tray sizes. Any user-facing pick-sequence output must add +1 to tile_id for display labels. When the user asks about solvability, clarify whether they mean "v3 unsolvable (no buffs)" or "unwinnable even with buffs".
