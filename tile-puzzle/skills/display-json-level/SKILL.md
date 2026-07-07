---
name: display-json-level
description: "Render a Tile Explorer LEVEL JSON (game format {group,tiles,layers,stacks,bg,bgm,sl,dif} with stones {i,x,y,(s),(m)}) into a self-contained, browser-playable HTML with real art — tilebase plate + Group_1 tile faces, bonus drawn ROUND, mission SQUARE, mystery face-down — faithful to the engine rules. Read-only display/preview; does NOT change the JSON."
when_to_use: "When the user wants to view / preview / play / 'display' a level JSON in the browser, share a playable single-file HTML, or visually check a generated level. Distinct from gen-layout (makes empty geometry) and tile-level-design (assigns tiles, scores difficulty, solves/verifies) — this skill only RENDERS an existing level file, it does not create or modify levels."
---

# display-json-level skill

Turn a finished level JSON into a **single self-contained `.html`** you can open in any browser (or
share). It does not touch the JSON — pure display. Works everywhere, incl. the claude.ai web sandbox:
the sandbox writes the file, the user downloads and opens it.

## The one command

```bash
python ${CLAUDE_PLUGIN_ROOT}/skills/tile-level-design/scripts/make_play_html.py <level.json> [out.html]
```

`out.html` defaults to `<level-basename>_play.html` in the current directory.

If `${CLAUDE_PLUGIN_ROOT}` is not set, use the absolute cache-path form (same convention as
tile-level-design SKILL.md §19):

```bash
python C:/Users/tamng/.claude/plugins/cache/toolgenlevel/tile-puzzle/<version>/skills/tile-level-design/scripts/make_play_html.py <level.json> [out.html]
```

The renderer lives in the **tile-level-design** skill (shared with `make_gallery_play.py`); this skill
references it rather than duplicating the ~1 MB of art assets.

## What it renders (faithful to the game)

- **Cover / pickable rule = the engine / Unity `IsCanPickUp` rule:** an upper tile covers a lower one
  iff `|dx| < 1` AND `|dy| < 1`, the **same for every tile including specials**. A special's big size
  is **RENDER-ONLY**, it does not change coverage — a special placed at a 2×2 centre (half-integer
  `x,y`) naturally covers the 2×2 cluster around it. A tile with nothing covering it is pickable.
- **Match-3 tray:** pick a tile → tray; 3 of a type auto-clears. **Game over** when tray length ≥ 7 and
  no type has 3. **Win** when every tile is cleared. Buffs: Shuffle / Undo / +1 Slot.
- **Specials (optional):** BONUS `1001` and MISSION `1002` are NON-match-3 covers — they never enter
  the tray and **AUTO-CLEAR (cascading) the moment nothing covers them** (same radius-1 rule). Render
  size = `s + 0.9` (≈ 1.4–2.4× a normal tile); **bonus draws as a circle, mission as a rounded
  square**; both dim while covered.
- **Mystery (`m:true`):** a normal match-3 tile shown FACE-DOWN (mystery cover art) until it becomes
  pickable, then it reveals its Group_1 face. Plays as a normal tile.
- **Art:** one random tilebase plate for the whole level + a Group_1 face per distinct tile type
  (display-only mapping — the `i` values in the JSON are untouched; a raw id that matches a Group_1
  filename uses that exact sprite). Only the images actually used are embedded as base64, so the file
  stays small. Falls back to coloured squares + unicode symbols if the `assets/` are missing.

Assets are bundled at `tile-level-design/assets/` (`tile_faces/` from Group_1, `tilebase/`).

## Overlap / stacking rule (the one thing to get right)

This is the model the display MUST match. It is the authoritative game rule — reverse-engineered and
verified against the engine (`engine/tile_level_simulator.py`: `_build_visibility` ~L783,
`compute_coverage` ~L1067), which the code comments trace to **Unity `IsCanPickUp` (0x150D6A8)**.

**The unit-square model.** Every tile — normal, mystery, bonus, mission — is a **1×1 UNIT square
centred at its `(x, y)`**. The render size `s` (bonus `1.5`, mission varied; drawn at `s + 0.9` ≈
1.4–2.4×) is **RENDER-ONLY** — a decorative frame. It plays NO part in collision.

**Pickable rule (binary).** A tile is **covered / unpickable** iff some ACTIVE tile on a strictly
**HIGHER layer** overlaps it: `|dx| < 1` AND `|dy| < 1`. Otherwise it is pickable. Same rule for every
tile, specials included.

- **Half-grid stagger ⇒ 2×2 cover.** Tiles on adjacent layers sit at a `0.5` offset; `|dx| = 0.5 < 1`,
  so ONE upper tile covers the ~**4 lower tiles** (the 2×2) beneath it. A "centre" tile that looks
  half-exposed under four staggered neighbours is correctly unpickable until those four clear — **not a
  bug**.
- **Specials, same rule.** A bonus/mission drawn at 2.4× still only blocks the cells its 1-unit
  footprint overlaps. Placed at a 2×2 centre (half-integer `x,y`) it covers exactly that 2×2 and
  **auto-clears the moment nothing covers it** by this same rule.
- **`compute_coverage` is NOT this.** The engine's 4-corner `compute_coverage` (returns 0–4) feeds only
  the **cover100 difficulty score** — it is NOT the pickability test. Do not conflate the two: coverage
  = a scoring metric, `IsCanPickUp` = the binary any-overlap rule above.
- **Placement, not rendering, is the failure mode.** Because collision is 1-unit but the frame is big,
  a special is only visually honest when it sits at a **2×2 centre**. A mis-placed special's frame
  visually overhangs tiles it does NOT block — that *looks* like an overlap bug but the logic is
  correct; fix it by authoring specials at 2×2 centres (see `reserve_special.py`, which does this).

Because the player uses exactly this rule, **what you see = what actually plays** — cross-checked:
player `isPickable` == engine `_build_visibility` pickable set on every cell of the reference levels,
and it matches `verify_smart_v3` / `solve_v3_special`.

## Worked example

```bash
# render a generated level to a shareable single-file player
python ${CLAUDE_PLUGIN_ROOT}/skills/tile-level-design/scripts/make_play_html.py levels/Level_Circle_game.json Level_Circle_play.html
# -> SAVED Level_Circle_play.html  (open in any browser; real art embedded)
```

Then hand the `.html` to the user (e.g. via SendUserFile) — it is a complete, shareable, offline
playable page.
