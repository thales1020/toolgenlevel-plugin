# Changelog — tile-puzzle

## 0.3.3

- **MYSTERY tile (`m:true`) formalised.** Confirmed from the `NewLayout_L*M` reference set: a mystery
  tile is a NORMAL match-3 tile that is merely FACE-DOWN to the player — colour fixed at design time,
  hidden only visually. Every reference board stays ÷3 WITH mystery tiles counted, so it changes
  nothing about geometry, match-3 balance, or solvability (no solver work needed — unlike bonus/mission).
  `tile-level-design/scripts/add_special_cells.py` now exposes `--mystery N` (canonical; `--mark` kept
  as alias) and defaults to a random 3-5 tiles (the reference convention) when no count is given. Added
  as the LAST post-tile step; no re-verify required. SKILL §23 updated.
- **`reserve_special.py` can combine bonus + mission in ONE level.** New `--bonus N` / `--mission M`
  flags reserve both special types in a single pass (running the old `--id/--n` twice would wipe the
  first via `clear_tiles()`); both kept out of the match-3 pool, verified together with
  `solve_v3_special(special_ids=(1001,1002))`. Legacy `--id/--n` still works.
- **Reference-accurate special render sizes.** Reverse-engineered `s` from the BonusLevel + MissionTile
  sets: BONUS (1001) is always **1.5** (or absent) — fixed. MISSION (1002) is **varied** — early/mid
  levels (L30-120) MIX a small base (0.6, sometimes 0.55) with occasional larger accents (0.9, rarely
  1.2) within one level; late levels (L130-300) are uniform 0.7. `reserve_special` now emits bonus 1.5
  and per-tile MIXED mission sizes by default (the L30-120 style); `--size` still overrides all.
- **`make_play_html.py` models specials.** The browser player now faithfully renders bonus/mission as
  non-pickable covers that AUTO-CLEAR (cascading) when uncovered, and mystery tiles face-DOWN (`?`)
  until pickable — matching `solve_v3_special`. Undo now snapshots the full board so special cascades
  restore correctly. Normal levels are unaffected (no `i>=1001` / `m`).

## 0.3.2

- **`tile-level-design/scripts/test_special_solver.py`** — regression test locking the special-tile
  solver's soundness: auto-clear semantics (special covers below + clears free when exposed), reduction
  (matches engine `solve_v3` on no-special boards), and end-to-end reserve verification. 6/6 PASS.

## 0.3.1

- **`tile-level-design/scripts/solve_special.py`** (`solve_v3_special`) — a v3 DFS that models special
  AUTO-CLEAR: bonus/mission tiles stay in the board as covers and clear for free the moment they're
  exposed (cascading), match-3 branches over normal tiles only. This is the RIGOROUS solvability check
  that replaces the 0.3.0 shortcut (which excluded specials from the solve). `reserve_special.py` now
  verifies on the FULL board via `solve_v3_special`. The engine `verify_smart_v3.py` is unchanged
  (byte-identical / parity-locked) — the auto-clear solver lives in the skill's scripts/.

## 0.3.0

Special cells (stack / bonus / mission / mark) + exact game-format export. All OPTIONAL.

- **`gen-layout/scripts/add_stacks.py`** — add straight-stack columns (`stacks:[{x,y,d}]`) to an empty
  layout as a GEOMETRY step (before tiles). Pattern placement (edge/ring/corners) and SYMMETRY-
  preserving (detect the layout's group, place full mirror orbits, re-impose symmetry → stays 1.00).
- **`tile-level-design/scripts/reserve_special.py`** — reserve BONUS (`1001`) / MISSION (`1002`) tiles
  the correct way: these are NON-match-3 slots that auto-clear when uncovered (`total − count(special)`
  is ÷3 in 100% of reference files). Pre-sets N cells to the special id, assigns match-3 to the REST
  (trimmed to ÷3), verifies v3-solvable on the match-3 board. (NOT a post-tile retype — that breaks
  solvability.)
- **`tile-level-design/scripts/add_special_cells.py`** — slimmed to the `m:true` MARK overlay on
  normal tiles (post-tile; the mission part moved to reserve_special).
- **`tile-level-design/scripts/export_game_format.py`** — export to the exact game LEVEL format
  `{group,tiles,layers,stacks,bg,bgm,sl,dif}` (drops `metadata`; `sl=2`,`dif=1` constant). Verified
  byte-shape-identical to the reference Mission/Bonus files. Run as the final step.
- SKILL docs: gen-layout file-tree + tile-level-design §23 "Special cells".

## 0.2.1

- **Symmetry is now the PRIORITISED DEFAULT** (`gen_shape_layout` / `gen_region_depth`): `--mirror` is
  ON by default with `--axis auto` — the script measures the shape's natural reflection axes and snaps
  the largest group it supports (circle→d4, heart→vertical, sword→none/not-forced). This fixes the
  intermittent "a circle sometimes came out not symmetric" — symmetry no longer depends on remembering
  a flag. Per-layer and coverage symmetry are guaranteed by construction. `--no-mirror` opts out.

## 0.2.0

gen-layout overhaul: aesthetics + symmetry first, image pipeline hardened.

### gen-layout
- **Bulk generation retired.** Removed the `empirical` / `abstract` / `symmetric` / `mixed` modes and
  their data banks — they could not guarantee per-board symmetry/aesthetics at scale (empirical kept
  only ~8% of boards perfectly symmetric vs ~66% for real boards). gen-layout now composes **one
  symmetry-ranked layout at a time**.
- **4-axis symmetry, measured & ranked.** Every layout records `symmetry_axes` (vertical, horizontal,
  diag, anti-diag), `symmetry_best_axis`, `symmetry_score`. `--mirror` snaps; `--min-sym` gates.
- **Match the source object's symmetry.** New `--axis {vertical, horizontal, vh, d4}`:
  count the image's reflection axes and build the same — `vh` (2 orthogonal axes) and `d4`
  (all 4 reflection axes, mandala/tile motifs) union the symmetry orbit + orbit-repair support → all
  that group's axes read exactly 1.00, valid & playable.
- **Simplify-first.** The shape path auto-runs the complexity gate (`evaluate_icon`) and warns when
  over budget (>~48 footprints / aspect >1.1) — simplify a complex image, don't chase literal fidelity.
- **Image-path symmetry fix.** `gen_shape_layout` / `gen_region_depth` now measure + record symmetry
  (the old peel/trim dropped single off-axis cells; the +0.5 stagger left even layers asymmetric).
- **SVG→mask parser hardened.** Single-quote attributes, `transform` (translate/scale/matrix/rotate),
  and `fill:none`/stroke now handled — before, these silently produced an empty or garbled mask.
- **gen_region_depth.** Lazy Pillow import, `--heights` CLI, `--auto` grid detection (best-effort),
  bounds guard, deep-tower-protecting trim (`shallow`), true L0 silhouette review render, symmetry
  metadata + `--axis vh/d4`.
- **render_png.** Empty-layout guard, 12-colour palette (L0≠L8/L12), deep-layer inset clamp.

### tile-level-design
- Unchanged in 0.2.0 (engine parity maintained with gen-layout).

## 0.1.0

Initial packaged plugin: gen-layout + tile-level-design, marketplace + auto-provision, frontmatter
fix (B6), B1–B5 fixes from the live game-designer test.
