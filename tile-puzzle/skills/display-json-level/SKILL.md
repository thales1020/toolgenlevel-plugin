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
python <plugin-cache>/toolgenlevel/tile-puzzle/<version>/skills/tile-level-design/scripts/make_play_html.py <level.json> [out.html]
# <plugin-cache> = ~/.claude/plugins/cache  (e.g. C:/Users/<you>/.claude/plugins/cache on Windows)
```

The renderer lives in the **tile-level-design** skill (shared with `make_gallery_play.py`); this skill
references it rather than duplicating the ~1 MB of art assets.

## What it renders (faithful to the game)

- **Cover / pickable rule (footprint overlap):** an upper tile covers a lower one iff their footprints
  overlap — `|dx| < halfA+halfB` AND `|dy| < halfA+halfB`. A NORMAL tile is 1×1 (half `0.5`); a SPECIAL
  is a **2×2** (half `1.0`) OR **3×3** (half `1.5`) object read from its `s` (see below). So
  normal↔normal `= 1.0` (identical to the engine — no-special boards unchanged). A tile with nothing
  covering it is pickable.
- **Match-3 tray:** pick a tile → tray; 3 of a type auto-clears. **Game over** when tray length ≥ 7 and
  no type has 3. **Win** when every tile is cleared. Buffs: Shuffle / Undo / +1 Slot.
- **Specials (optional):** BONUS `1001` and MISSION `1002` are NON-match-3 covers — they never enter
  the tray and **AUTO-CLEAR (cascading) the moment their WHOLE footprint is clear on top**. The footprint
  comes from `s`: **mission `0.7` = 2×2, `1.0` = 3×3; bonus `1.0` = 2×2, `1.5` = 3×3**. The special
  RENDERS at exactly that footprint (2 or 3 cells) so **visual = collision**; **bonus draws as a circle,
  mission as a rounded square**; both dim while covered.
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

**The footprint model.** A NORMAL / mystery tile is a **1×1 unit square** centred at `(x, y)` (half
`0.5`). A SPECIAL is a bigger square whose size is read from its `s`:

| footprint | collision half | centre parity | mission `s` | bonus `s` |
|---|---|---|---|---|
| **2×2** | `1.0` | half-integer | `0.7` | `1.0` |
| **3×3** | `1.5` | integer | `1.0` | `1.5` |

(thresholds: mission `s ≥ 0.85 → 3×3`; bonus `s ≥ 1.25 → 3×3`; else 2×2). The special RENDERS at exactly
this footprint, so the frame == what it blocks — **visual = collision**, no decorative overhang.

**Pickable rule (binary).** A tile is **covered / unpickable** iff some ACTIVE tile on a strictly
**HIGHER layer** overlaps its footprint: `|dx| < halfA+halfB` AND `|dy| < halfA+halfB` (partial overlap
counts). normal↔normal `= 1.0` (== the engine); a 2×2 special↔normal `= 1.5`; a 3×3 special↔normal `= 2.0`.

- **Half-grid stagger.** Tiles on adjacent layers sit at a `0.5` offset; `|dx| = 0.5 < 1`, so ONE upper
  normal covers the ~4 lower tiles beneath it. A "centre" tile that looks half-exposed under four
  staggered neighbours is correctly unpickable until those four clear — **not a bug**.
- **Specials cover their WHOLE footprint.** A special blocks every tile under its 2×2/3×3 and
  **auto-clears only when its ENTIRE footprint is clear on top** (not just its centre). Because render ==
  footprint, this reads correctly on screen.
- **`compute_coverage` is NOT this.** The engine's 4-corner `compute_coverage` (returns 0–4) feeds only
  the **cover100 difficulty score** — NOT pickability. Do not conflate: coverage = a scoring metric.
- **Stay within the layout.** `reserve_special.py` places a special only where its whole footprint fits
  inside the layout bounds and ≥1 tile still covers it at start (so it doesn't auto-clear immediately).

Because the player, `solve_v3_special`, and `reserve_special` all derive the footprint from `s` the
same way, **what you see = what actually plays** — cross-checked: player `isPickable` and
special-covered-at-start match the solver's visibility on every cell (2×2 and 3×3 levels).

## Worked example

```bash
# render a generated level to a shareable single-file player
python ${CLAUDE_PLUGIN_ROOT}/skills/tile-level-design/scripts/make_play_html.py levels/Level_Circle_game.json Level_Circle_play.html
# -> SAVED Level_Circle_play.html  (open in any browser; real art embedded)
```

Then hand the `.html` to the user (e.g. via SendUserFile) — it is a complete, shareable, offline
playable page.
