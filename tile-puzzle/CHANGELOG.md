# Changelog — tile-puzzle

## 0.5.4

Aligns the generators/scorer to the game designer's authoritative spec docs
(TileLevel_AI_KnowledgeBase §4-7, LevelFormat_Standard). Audited every requirement against the code;
fixed the divergences below (footprints/thresholds, `sl`, interstitial even/odd, injective sprites
already matched — untouched).

- **Special placement now enforces all 7 rules** (`reserve_special.py`, §5.1). Added the three that were
  missing/partial: **(4) never overlaps a STACK column**; **(5) distinct (x,y)** — two specials can no
  longer share a coordinate on different layers; **(7) even layer spread** — farthest-first + prefer the
  interstitial layer with the fewest specials (was: pile all onto the highest layer). **Rule 6 hardened**
  from "distinct layers" to "a NORMAL tile must sit on a layer BETWEEN two overlapping specials" — this
  blocks the chain-reveal / "mission tự biến mất" auto-clear at generation time (unit-tested).
- **Cloud symmetry is now HYBRID, coverage 15-20%** (`add_cloud.py`, spec PHẦN 6 / bug #10). The old hard
  symmetry gate left ~1/4 of cloud levels with 0 clouds; now symmetric orbits fill first, then any
  covered+visible cell tops up to target — never 0 clouds when candidates exist. Default `--cloud-pct`
  33 → 18.
- **Mystery count is context-aware + evenly placed** (`add_special_cells.py`, spec PHẦN 7 / bug #11).
  Default count: **5** alone / **4** with Mission/Bonus / **3** with Cloud (was random 3-5). Placement is
  now EVEN across layers, **≤2 per layer**, only over layers holding a real normal tile.
- **`new_diffScore` n_types collapses specials** (`diff_score.py`, spec §4.1). Bonus (1001) + Mission
  (1002) count as ONE type bucket, not two — a mixed mission+bonus level is +1, not +2. Mission-only /
  bonus-only unchanged.

## 0.5.3

- **Fixed the 3-tiles-do-not-match display bug.** Two DIFFERENT tile types could be drawn with the SAME
  Group_1 face sprite (looked identical but never matched). make_play_html now maps types to sprites
  INJECTIVELY: exact-id sprites are claimed first, every other type takes an UNUSED sprite. Affected 11
  reference levels mixing in-range (85,142-170) and out-of-range tile ids; 0 collisions after the fix.
- **Re-audited solvability with the special tiles.** An independent player-mechanic DFS (footprint-aware
  pickability + special auto-clear + tray-7 match) AGREES with solve_v3_special on 6/6 levels
  (bonus/mission mix, cloud, mystery, combined, reference) — no player/solver divergence. cloud/mystery
  are plain match-3 tiles (o/m display-only): per-type divisible-by-3 and solvability unchanged.

## 0.5.2

- **BONUS render-size `s` remapped**: bonus 2×2 = **0.9** (was 1.0), 3×3 = **1.4** (was 1.5); read-back
  threshold `s ≥ 1.15 → 3×3`. Collision footprints unchanged (half 1.0 / 1.5). Updated in lock-step across
  `reserve_special._emit_s`, `solve_special.footprint_half`, `make_play_html.specHalf` + SKILL §23.
  Mission unchanged (0.7 / 1.0).

## 0.5.1

- **MYSTERY tile moved to the `o:[0]` format + reveal-on-pick.** The mystery marker is now `o:[0]` (the
  same `o` field as cloud: 0=mystery, 1=cloud); the old `m:true` is LEGACY (still READ by the player and
  diff_score, but `add_special_cells.py --mystery N` now GENERATES `o:[0]`). Reveal timing fixed to match
  the game: a mystery tile stays FACE-DOWN on the board **even when pickable** — it is picked BLIND and its
  real colour shows only once it lands in the TRAY (distinct from CLOUD, which reveals on-board the instant
  it is uncovered). `make_play_html.py` splits the two reveal rules; a covered mystery is still clickable
  (blind pick). `diff_score.py` `is_mystery` now counts `o:[0]` OR legacy `m:true`. Placement unchanged
  (3-5 random, any layer). No solvability impact. SKILL §23 updated.

## 0.5.0

- **New CLOUD tile (`o:[1]`).** A NORMAL match-3 tile (real colour, matchable, counts ÷3) carrying an
  extra stone field `"o":[1]`, covered by the `tile_cover_mystery` art; the cover clears MISSION-STYLE
  — the instant nothing on a higher layer overlaps it (= when it becomes pickable) — revealing the real
  face. NO solvability impact (the solver ignores `o`). The `o` value encodes type: 1=cloud (0=mystery,
  a future variant).
  - **`tile-level-design/scripts/add_cloud.py`** (post-tile overlay, like add_special_cells): marks
    normal tiles as clouds on the BOTTOM layer(s) 0-1 only (never the top — a cloud must start covered),
    100% covered-at-start, as a SYMMETRIC region (auto-detected axis, ≥ vertical), ~33% of tiles by
    default (`--cloud-pct` / `--cloud N`, `--axis`, `--layers`). Reproduces the reference stats
    (game-data/CloudTile: 23-47% of tiles, layers 0-1, all covered, symmetric).
  - **Candidate cells must be COVERED *and* VISIBLE (peek)** — no tile directly on top (within 0.5) —
    so the cover actually shows. Cloud levels therefore REQUIRE a **STAGGERED layout** (gen-layout
    default `uniform_stagger`); on a COLUMNAR layout every bottom cell is fully hidden and add_cloud
    places 0 (it logs the shortfall + suggests a staggered layout rather than burying clouds).
  - **`make_play_html.py`** renders a cloud (and mystery) with the cover art filling the WHOLE tile
    (was a small 78% badge on a base plate); when it becomes pickable only the COVER clears, revealing
    the real Group_1 face — the tile itself stays and plays as a normal match-3 tile.
  - **`export_game_format.py`** preserves `o` (stone fields i,x,y,s,m,o copied as-is).
  - SKILL §23 documents CLOUD (incl. the staggered-layout requirement).

## 0.4.3

- **`reserve_special` — AUTO-MIX footprints by default.** `--mission N` / `--bonus N` with NO
  `--*-cover` flag now auto-mixes 2×2 and 3×3 specials (`n_3x3 = N//2`, rest 2×2 — so N=4 → 2+2, N=5 →
  2×3×3+3×2×2; ≥1 of each for N≥2). Force uniform with `--mission-cover/--bonus-cover 2x2|3x3`; explicit
  `--mission-2x2/--mission-3x3` counts still compose.
- **`solve_special` — close the bare-file 3×3 divergence** (audit). Added `special_halves_from_level(data)`
  which builds the `{(x,y,layer): footprint_half}` map from a level JSON's `s` values, and a CLI
  `python solve_special.py <level.json>` that uses it — so solving a FILE models 3×3 specials as 3×3,
  not the optimistic 2×2 default. Docstring example updated. (`reserve_special` already passed its map.)
- **Docs de-staled** (audit): `tile-level-design/SKILL.md` §23 rewritten to the current model
  (direction-C interstitial covers over a ÷3 board, 2×2/3×3 footprint from `s`, stacking, offset
  placement, derived `sl`) — dropped the old "reserved slot / match-3 pool EXCLUDES", old render-`s`
  (bonus 1.5 / mission 0.6-1.2), and "sl=2 constant" text. `display-json-level/SKILL.md` machine-specific
  cache path replaced with a `<plugin-cache>` placeholder.

## 0.4.2

- **`new_diffScore` — the validated player-difficulty formula is now the recommended difficulty rank.**
  `scripts/diff_score.py` computes `max(0, -28.42 + 0.655·intra_group + 0.804·cover100 + 2.897·n_types +
  22.76·is_mystery)` — fit + validated on ~55K real plays of the live Pyramid game (LOO-CV Spearman
  0.615 all / 0.732 plain-only; source: docs/HANDOFF_KNOWLEDGE.md §4.3). `analyze_level.py` now prints
  `new_diffScore` + tier FIRST, and the old 5-component `final_score` is demoted to "OLD chaos-score
  (visual complexity, NOT player-difficulty)" — kept only as a feature (its `intra_group`+`cover100`
  feed new_diffScore) and for score-band screening. SKILL §3 rewritten around new_diffScore + its tier
  guide + the known static-only limitation (under-rates mechanics; the mystery term over-rates easy
  mystery boards).
- **`export_game_format.py` — `sl` is now derived from special content, not hardcoded.** Was always
  `sl=2`; now: a MISSION level (any i=1002) → `sl=2`, else a BONUS level (i=1001) → `sl=1`, else a
  normal / mystery-only level → the `sl` key is OMITTED (verified: BonusLevel=1, MissionTile=2,
  mystery-only L*M have no sl). `dif=1` and key order unchanged.

## 0.4.1

- **Special FOOTPRINT is now 2×2 OR 3×3, driven by the stone's `s`** (unified across player, solver,
  and generator): **mission `0.7` = 2×2 / `1.0` = 3×3; bonus `1.0` = 2×2 / `1.5` = 3×3** (2×2 = collision
  half 1.0, centre on a half-integer; 3×3 = half 1.5, centre on an integer). A normal tile stays 1×1.
  - `make_play_html.py`: `specHalf(t)` reads the footprint from `s`; the special renders at exactly that
    footprint (2 or 3 cells) so visual = collision.
  - `solve_special.py`: `_build_visibility_2x2` takes a `special_halves` map `{(x,y,layer): half}`
    (Cell is `__slots__`-locked); `footprint_half(sid, s)` is the shared s→half rule. Reduction preserved.
  - `reserve_special.py`: `--mission-cover {2x2,3x3}` / `--bonus-cover {2x2,3x3}` (default 2x2); places a
    special only where its whole footprint fits **within the layout bounds** and covers ≥1 tile (partial
    cover allowed — no longer requires a full cluster); emits the matching `s`; verifies footprint-aware.
  - Cross-checked player == solver (pickable + covered-at-start) on mixed 2×2/3×3 levels;
    `test_special_solver.py` 14/14 (adds a 3×3 group; reduction 12/12).
  - display-json-level SKILL.md overlap section updated with the s→footprint table.
- **Mixed footprints + overlapping specials STACK on distinct layers.** `reserve_special` gains
  `--mission-2x2/--mission-3x3/--bonus-2x2/--bonus-3x3` to MIX 2×2 and 3×3 specials in one level, and
  specials MAY now overlap. Fix: two OVERLAPPING specials no longer land on the same interstitial layer
  (which made neither cover the other, so a lower one auto-cleared while an overlapping special still sat
  on it) — `_find_placements` offers every valid interstitial layer and the assignment forces overlapping
  specials onto DISTINCT layers, so the higher genuinely covers the lower. The covered-at-start gate now
  counts a higher SPECIAL as a cover too (a lower special in a stack is covered by the one above; the top
  of each stack still needs a normal). Verified: mixed 5-special level → 0 same-layer overlaps, 0 specials
  auto-clear at start, solvable, normals ÷3.
- **Specials placed OFFSET (straddling), not snug in a cluster.** `_find_placements` now draws centres
  from a 0.5 grid (neat cluster centres AND ~½-cell-offset ones) and PREFERS the offset positions —
  scored by a "straddle" count (cells whose centre lies in the footprint's outer band, i.e. only ~half
  covered). So a mission/bonus sits shifted ~½ a cell and MANY normals each cover only half of it (it
  peeks out around them, like the real game) instead of nesting exactly on a 2×2/3×3 cluster. Ordering:
  highest interstitial layer (visible) → most straddle (offset) → fewest coverers. All invariants kept
  (within bounds, covered-at-start, overlapping specials stack on distinct layers, normals ÷3, solvable).
  Demo: each special ends up with ~4 half-covering normals (vs 0 for a neat placement); player == solver
  123/123, covered-at-start 3/3.

## 0.4.0

- **New skill `display-json-level`.** Renders a Tile Explorer level JSON into a self-contained,
  browser-playable single-file HTML (works everywhere incl. the claude.ai web sandbox). Read-only
  display — does not change the JSON. It references the `tile-level-design` renderer rather than
  duplicating assets.
- **`make_play_html.py` now renders REAL ART.** A random tilebase plate per level + Group_1 tile faces
  (a face per distinct type; a raw id matching a Group_1 filename uses that exact sprite). Bonus draws
  as a **circle**, mission as a **rounded square**, mystery **face-down** until pickable. Cells are
  SQUARE and a special renders at its exact **2×2 footprint** (so a bonus is a true circle and the frame
  equals what it blocks — no decorative overhang). Only images actually used are embedded (base64) so
  files stay small; falls back to coloured squares if assets are missing. Art bundled at
  `tile-level-design/assets/` (`tile_faces/` from Group_1, `tilebase/`).
- **Collision model: normals 1×1, SPECIALS 2×2.** A normal tile is a 1×1 unit (engine / Unity
  `IsCanPickUp` `|dx|<1 & |dy|<1`). A special (bonus/mission) is a **2×2 object** — it covers / is
  covered by its whole 2×2 footprint (partial overlap counts), so it auto-clears only when the ENTIRE
  2×2 is clear on top (not just its centre) and its render exactly matches what it blocks (visual =
  logic).
- **Solver aligned to the 2×2 special model.** `solve_special.py` now builds a special-aware visibility
  (`_build_visibility_2x2`): an upper cell blocks a lower one iff their footprints overlap
  `|dx| < halfA+halfB` with half = 1.0 for a special / 0.5 for a normal (normal↔normal = 1.0 —
  identical to the engine, so no-special boards are unchanged and the reduction property holds;
  special↔normal = 1.5, special↔special = 2.0). The player, `solve_v3_special`, and `reserve_special`
  now agree exactly (cross-checked: pickable + special-covered-at-start match on real levels). This
  resolves the earlier 1×1/2×2 pending caveat. `test_special_solver.py` gains a 2×2-semantics group
  (10/10 PASS incl. reduction 12/12).
- **`reserve_special.py` rewritten — direction C (specials are ADDED, never reserve a cell).** The old
  version retyped a normal cell to 1001/1002 (wrong: it consumed a match-3 slot and mis-placed the
  special). The reference data proves specials are ADDITIONAL interstitial covers over a COMPLETE ÷3
  normal board. New algorithm: assign a full v3-solvable normal level → renumber normals onto EVEN
  layers → place each special on the ODD layer between, at a **2×2 centre** (half-integer x,y) chosen so
  a higher normal still covers it at start (so it does NOT auto-clear immediately). No normal is removed
  (match-3 stays ÷3). HARD-verified: `solve_v3_special` True, every special covered at start, normals ÷3.
  This fixes the special visual/collision mismatch at the source — the big 2.4× frame now sits exactly
  on the 2×2 it covers. `--bonus/--mission` (and legacy `--id/--n`) unchanged.
- **`display-json-level` SKILL.md** gains an authoritative "Overlap / stacking rule" section (unit-square
  1×1 collision, render size is decorative, `compute_coverage` 0–4 is scoring-only and NOT pickability,
  mis-placement is the failure mode not the rule) — traced to engine `_build_visibility` / Unity IsCanPickUp.

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
