---
name: Tile Explorer game rules & solver bugs
description: Non-obvious game rules and solver pitfalls that bit me during level-design work
type: project
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Tile label display is internal_id + 1 (off-by-one).** The JSON/solver uses 0-indexed tile_ids (0-11 for 12 types). The play UI shows them as 1-indexed labels (1-12). When showing a solution path to the user, always map `display_label = tile_id + 1`. I hit this when the user said "I see tile 10, 4, 7, 7, 8" but my JSON had [9, 3, 6, 6, 7] — they're the same, offset by 1.

**Tray game-over rule is `size >= 7 AND no triple`, NOT `size > 7`.** From `tile_level_simulator.py:2721-2728` (`PlayWindow._on_click`): after insert + auto-clear, if tray length ≥ 7 with no count ≥ 3, game over fires. My first beam/DFS solvers used `> TRAY_SIZE` (overflow check) which allowed tray=7 states and produced "valid solutions" that instantly lose in the real game. Fix: `(tsize + 1) >= TRAY_SIZE` skip.

**Atomic triple optimization in DFS must bounds-check intermediate tray size.** When doing a "pick 3 of same type" atomic action, intermediate state between pick 1 and pick 3 has tray size `cur_tsize + (needed-1)` before the clear fires. That intermediate must be `< TRAY_SIZE`. I originally only checked the final size, which let invalid solutions through.

**Shuffle booster has been modified to guarantee an immediate triple after use.** The stock `_use_shuffle` did a plain `random.shuffle` of active tile IDs across cells. The custom version (see `tile_level_simulator.py:2764`) picks the remaining type with the most copies (≥3 required), force-places 3 of that type on random pickable cells, then shuffles the rest. Fallback: if no type has ≥3 copies OR < 3 pickable cells, plain random shuffle.

**v3 solvers do NOT model buffs.** `verify_smart_v3`, `solve_path`, and `count_solutions` all solve the level with tray=7 hard ceiling and no Shuffle/Undo/+1Slot. A level flagged "unsolvable" by v3 may still be beatable in-game via buffs — treat "v3 unsolvable" and "unwinnable" as different bars.

**Why:** These are all one-slot-off / one-rule-off bugs that look correct until you actually replay the solution in the game UI. Each one wasted multiple iterations to track down.

**How to apply:** Any new solver or replay script I write MUST use `>= TRAY_SIZE AND no triple` as the game-over check, and any atomic/batch action must validate intermediate tray sizes. Any user-facing pick-sequence output must add +1 to tile_id for display labels. When the user asks about solvability, clarify whether they mean "v3 unsolvable (no buffs)" or "unwinnable even with buffs".
