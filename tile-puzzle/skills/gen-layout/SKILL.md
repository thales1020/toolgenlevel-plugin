---
name: gen-layout
description: "Create an empty multi-layer LAYOUT (cell geometry, NO tiles) for the Tile Explorer Triple Match game — from a prose shape or an icon/image, ONE symmetry-ranked layout at a time (aesthetics + 4-axis symmetry prioritised). Upstream tool: outputs an empty NewLayout_*.json that the tile-level-design skill then fills with tiles. Does NOT assign tiles or score difficulty."
when_to_use: "When the user wants a NEW layout/template/shape (heart, duck, sword…) or an icon→layout. If the user wants a LEVEL from an image/shape, run gen-layout FIRST, then tile-level-design fills tiles. NOT for producing a playable level with tiles/difficulty — that is the tile-level-design skill (which has its own layouts). Bulk layout generation was retired — compose layouts one at a time."
---

# gen-layout skill

Creates **empty layouts** (cell positions across layers, NO tiles) → `NewLayout_<name>.json` (stones format), fed into **tile-level-design** which assigns tiles + scores difficulty.

**Layout = template (geometry only). Level = layout + tiles.**

---

## 1. READ EXPERIENCES.md FIRST

`EXPERIENCES.md` is the **token prior** — the learned NL experience library in the sense of Training-Free GRPO (arXiv 2510.08191). Claude (the frozen policy) reads it and CONDITIONS every layout generation on it. Do not generate without reading it.

Core rule from EXPERIENCES.md: **SPARSE-DEEP, never solid-shallow.** Real boards = small scattered base (~16 cells), towered ~6 layers, fill ~0.46 (NOT a solid blob).

---

## 2. One mode: compose (ONE layout at a time, symmetry-ranked)

gen-layout makes **one well-composed layout per call** from a shape/prose/image. **Aesthetics and
symmetry are the top priority.** Bulk generation was retired (see §4).

| Request | How |
|---|---|
| **A shape / prose** ("a sword", "a key", "this logo") | Claude reads EXPERIENCES → designs `[x,y,height]` anchors → `gen_layouts.py --mode compose` (`claude_compose.compose`) |
| **A recognizable icon/animal/image** | mask → `gen_shape_layout.py` (crisp silhouette; §3 note) |

**Symmetry is MEASURED on 4 axes and RANKED, never forced** ("đo & xếp hạng, không ép"):
`vertical` (left-right), `horizontal` (top-bottom), `diag_main` (/), `diag_anti` (\\). Every compose
writes `symmetry_axes`, `symmetry_best_axis`, `symmetry_score` (max of the 4) into metadata, and the
CLI prints them. Symmetric objects → `mirror=True` on the right axis → that axis scores **1.00**;
elongated/asymmetric objects → `--no-mirror` (kept recognizable, lower score is OK).

**Why Claude, not a parametric generator:** **only Claude** can make a recognizable novel shape
in-distribution (e.g. a sword as diagonal/sparse/deep like the competitor's level15 sword — a sampler
cannot take "make a sword"). Code only renders coordinates + measures symmetry deterministically.

---

## 3. Compose mode — step by step

> **Recognizable shapes (icon/animal/logo)? Use the AESTHETIC path, NOT raw `compose()`.**
> `compose()` gives every base cell a lone +0.5 tower → the rim fringes into a checkerboard.
> **SIMPLIFY THE IMAGE FIRST — the board space is SMALL** (real boards ~16–24 base footprints, ~6
> layers, mobile-portrait aspect ~0.88). A detailed/complex picture **cannot** be reproduced
> faithfully: reduce it to a **low-res recognizable silhouette**, drop small features, accept "reads
> like the idea" over pixel-faithful. Then: build a 2D mask → **verify the FLAT silhouette reads** →
> `python ${CLAUDE_SKILL_DIR}/scripts/gen_shape_layout.py --mask m.txt --name duck --layers 5 [--target 180] [--mirror] [--min-sym 0.8]`.
> It **auto-runs the complexity gate** (`evaluate_icon`) and **warns when over budget** (>~48
> footprints / aspect >1.1 → simplify); defaults to **EVEN** depth (`--mound` = central mound);
> **MEASURES symmetry on 4 axes**, and `--mirror --axis …` snaps to score **1.00** (`--min-sym`
> gates). Emits `_<name>_flat.png` (silhouette review) + `_<name>_stack.png`. See EXPERIENCES [8].
> Use bare `compose()` only for abstract/non-pictorial specs.
>
> **MATCH THE SOURCE OBJECT'S SYMMETRY (do this for every image):** first COUNT how many reflection
> axes the object in the image has, then build a layout with the SAME symmetry via `--mirror --axis`:
>
> | Object reflection axes | Example | Flag |
> |---|---|---|
> | **0** (asymmetric / directional) | sword, key, animal facing a way | `--no-mirror` (measure only) |
> | **1** vertical (left–right) | shield, heart, cup, front-facing face | `--mirror --axis vertical` |
> | **1** horizontal (top–bottom) | a fish in side view, a boat | `--mirror --axis horizontal` |
> | **2** (L-R **and** T-B) | ellipse, eye, rounded rectangle | `--mirror --axis vh` |
> | **4** (vert+hori+both diagonals, D4) | square decorative tile, mandala, flower medallion, snowflake | `--mirror --axis d4` |
>
> `vh`/`d4` union the symmetry orbit then orbit-repair support + div3 → that group's axes all read
> **1.00**, valid & playable. (Odd-fold symmetry — a 3- or 5-pointed star — doesn't map to the square
> grid; pick the nearest of the above, usually `d4` or `vertical`.)

Claude authors the layout spec, code renders it:

```
Step 1. Read EXPERIENCES.md top to bottom.
Step 2. Design anchor list: [(x, y, height), ...] following every experience.
        - Sparse: ~8–16 base anchors, not a filled grid
        - Deep: heights 4–8 (mean ~5)
        - CLASSIFY symmetry FIRST (text prompts only; an image already carries it — B5):
          · Symmetric object (shield, heart, cup, lantern…) → build half + mirror=True on the
            matching axis: `--axis vertical` (left-right, default) or `--axis horizontal` (top-bottom).
            compose drops mirror-PAIRS → that axis scores EXACTLY 1.00, no stray cells.
          · Elongated/asymmetric (sword, key, arrow, leaf…) → --no-mirror + DIAGONAL tilt to one
            side (EXP [2]); a diagonal also fits the mobile-PORTRAIT frame — never lay it wide (B4).
            Lower symmetry_score is EXPECTED here (not forced).
Step 3. Run: python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode compose --spec '<JSON>' --name <name> --out <dir>
        e.g.: python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode compose \
              --spec '[[0,0,6],[1,2,5],[-1,3,4],[2,4,3]]' \
              --name sword --no-mirror --out layouts/
        Optional gate: add `--min-sym 0.8` for a symmetric object → exit 2 + WARNING if the best of
        the 4 axes < 0.8, so you re-compose (ranks symmetry up without forcing it).
Step 4. Validate: read the printed `symmetry: vert/hori/diag/diag -> best …` line (symmetric shapes
        should hit best≈1.00 on the intended axis) + layout_diff (~5 target); inspect PNG (optional).
Step 5. Hand to tile-level-design: python <tile-level-design>/templates/find_trap_fast.py ...
```

**Worked example — sword:**
```python
# Sword = diagonal path from hilt (bottom) to tip (top), with guard crossbars
spec = [
    # hilt (bottom, wide, shallow)
    [-1, 0, 2], [0, 0, 3], [1, 0, 2],
    # blade (diagonal, deep)
    [0, 1, 6], [1, 2, 5], [2, 3, 5], [3, 4, 4],
    # tip
    [4, 5, 3],
]
# mirror=False (sword is asymmetric)
```

---

## 4. Bulk generation — RETIRED (do not bulk-gen layouts)

The bulk modes (`empirical` / `abstract` / `symmetric` / `mixed`) and their data banks
(`templates_bank.json`, `symmetric_components.json`, `excluded_sigs.json`) were **removed**.

**Why:** at scale, per-board symmetry/aesthetics could not be guaranteed. Measured on the real
sym-fraction metric, `empirical` kept only **~8%** of boards perfectly symmetric (real boards: ~66%),
with an ugly tail down to 0.32 — exactly the "xấu, bất đối xứng" the team reported. Quality of a
single layout > a pile of mediocre ones. gen-layout now does **one symmetry-ranked layout per call**.

If you genuinely need many layouts, compose them **one at a time** (each gets the 4-axis symmetry
check), or use the 120 bundled sample layouts in the `tile-level-design` skill.

---

## 5. Hard invariants (from game engine)

1. Every cell at L>0 must overlap >=1 cell directly below: `|dx|<1 AND |dy|<1`
2. Total cells % 3 == 0
3. >=3 pickable cells at start (no higher-layer cell covering them)
4. Alternating +0.5 stagger: even layers at integer coords, odd layers at +0.5
5. `compose()` handles invariants 1-4 automatically (support cleanup + div3 trim)

---

## 6. Output format -> tile-level-design

```json
{"group":1,"tiles":"","layers":[
  {"index":0,"stones":[{"x":-1.0,"y":0.0},...]},
  {"index":1,"stones":[{"x":-0.5,"y":-0.5},...]}
],"stacks":[],"metadata":{
  "layout":"sword","source":"claude_compose","n_layers":6,
  "total_tiles":54,"capacity":18,"layout_difficulty":5.2,
  "symmetry_axes":{"vertical":1.0,"horizontal":0.24,"diag_main":0.0,"diag_anti":0.0},
  "symmetry_best_axis":"vertical","symmetry_score":1.0}}
```

**tile-level-design loads it via:**
```python
board = load_board_from_file(abs_path("NewLayout_sword.json"))
```
Layout difficulty in metadata lets tile-level-design pick the right assignment strategy.

---

## 7. Updating EXPERIENCES.md

There are TWO ways the experience library grows. Both are Claude-in-the-loop (no code auto-writes
this file); both work on ANY machine/session running Claude Code with this skill — no project memory
or chat history required, because the lesson is written INTO this file, which travels with the skill.

### 7a. Learn from CHAT FEEDBACK (do this EVERY session — no data, no API needed)

**Whenever the user corrects or steers a layout in chat, distill the GENERALIZABLE lesson into an
EXPERIENCES entry before finishing.** This is how [8]–[11] were added. Trigger phrases: "chưa đẹp",
"dày hơn", "dàn đều", "to ra", "ưu tiên X", "không nên Y", or any accept/reject of a generated shape.
Procedure:
1. Restate the lesson in ONE general rule (not "the duck's tail" but "elongated protrusions read as
   spikes — keep them ≤2 cells / horizontal"). Drop session-specific nouns.
2. Append as `**[N]** (add, <topic> session) **<rule>**` with the EVIDENCE (what failed, what fixed it).
   If it refines an existing rule, `(modify, …)` that entry instead of duplicating.
3. If it changed a script default (e.g. `--even`), say so in the entry so the rule and code agree.
4. Keep it falsifiable + concrete (numbers, file names, the render that proved it).
Skip only if the feedback is a one-off cosmetic tweak with no transferable principle.

> The Training-Free GRPO loop (auto-learning EXPERIENCES from a real-boards corpus) was removed
> with the bulk pipeline. Update EXPERIENCES.md by hand from what each composed layout teaches.

---

## 8. Skill files

```
gen-layout/
  SKILL.md                  <- this file
  EXPERIENCES.md            <- token prior (learned shape/symmetry rules, updatable)
  LAYOUT_PRIORS.md          <- statistical priors from real boards (deep/sparse/symmetric)
  layout_priors.json        <- raw numbers
  engine/                   <- tile_level_simulator + verify_smart_v3 + solve_path + scoring_weights
  scripts/
    gen_layouts.py          <- CLI: --mode compose (the only mode; bulk retired) + 4-axis symmetry report
    claude_compose.py       <- spec -> rendered cell-set (mirror axis vertical/horizontal, or no-mirror)
    geom.py                 <- pure geometry + 4-AXIS symmetry scorer (sym_scores / geom_symmetrize / geom_div3_trim)
    gen_shape_layout.py     <- SHAPE layouts (icon/animal): mask -> capped_inset/even depth -> exact tile count [EXP 8,9]
    gen_region_depth.py     <- per-COLOUR-REGION depth from an image (beak/eye deeper than body) [EXP 10]
                               (--auto grid detect · --heights · --axis vertical|horizontal|vh|d4 · deep-tower-safe trim)
    gen_soda_cup_cov.py     <- hit an exact cover100 % (e.g. 50/75% completely covered) via 2-phase tuner [EXP 11]
    symmetrize_layout.py    <- enforce exact symmetry on an existing layout (geom-mirror)
    validate_layout.py      <- structural validity check
    render_png.py           <- optional visualization
    clone_layout.py         <- copy + resize/reshape a reference board
    fit_layout.py           <- hit exact tile count target
    target_difficulty.py    <- hit level-difficulty target after tile assignment
    test_full.py            <- test suite (14 tests, incl. compose + 4-axis symmetry)
    test_usecases.py        <- use case integration tests
```

---

## 9. Reference: real distribution targets (from LAYOUT_PRIORS.md)

| Feature | Real median | Acceptable range |
|---|---|---|
| n_layers | 6 | 4-8 |
| cells | 72 | 40-120 |
| base_fill | 0.46 | 0.25-0.70 |
| tower_mean | ~4 | 2-7 |
| n_clusters | 5 | 2-12 |
| sym_h | 0.64 (64%) | — |
| aspect (w/h) | 0.87 | 0.6-1.2 |
| layout_diff | ~5-6 | 3-10 |

A **solid filled silhouette** (fill ~1.0, n_clusters=1) is the #1 off-distribution pattern — never generate it.

---

## 10. Pipeline: image/shape → playable LEVEL (cross-skill)

A request like *"a level from this image, 50% of tiles 100%-covered, difficulty = X"* spans BOTH skills.
**Claude (main loop) orchestrates — skills do NOT call each other**; the hand-off is the
`NewLayout_*.json` file (a data contract).

1. **Order**: gen-layout builds geometry from the image → `NewLayout_*.json` → tile-level-design assigns tiles.
2. **Geometry sets the ceiling**: layout depth/cells cap achievable difficulty AND cover100; tiles dial only WITHIN it. Expose `layout_difficulty` + achievable score-range in metadata so the orchestrator knows the ceiling.
3. **Coupling**: cover100 is itself a score component — a coverage target and a difficulty target are NOT independent.
4. **Auto-retry (silent)**: target missed but feasible → regenerate deeper / more seeds before asking the user.
5. **Conflict → ask the user**: if constraints are PROVEN mutually infeasible, do NOT silently relax and do NOT ship a bad board. Diagnose quantitatively (which constraints clash, achievable vs requested) and let the user loosen ONE.

(Tile assignment, scoring, the `best`-tracker, and the always-solvable rule live in **tile-level-design**.)
