---
name: gen-layout
description: "Create empty multi-layer LAYOUTS (cell geometry, NO tiles) for the Tile Explorer Triple Match game — from a prose shape, an icon/image, or in bulk. Upstream tool: outputs empty NewLayout_*.json that the tile-level-design skill then fills with tiles. Does NOT assign tiles or score difficulty."
when_to_use: "When the user wants a NEW layout/template/shape (heart, duck, sword…), an icon→layout, or bulk layout geometry. If the user wants a LEVEL from an image/shape, run gen-layout FIRST, then tile-level-design fills tiles. NOT for producing a playable level with tiles/difficulty — that is the tile-level-design skill (which has its own layouts)."
---

# gen-layout skill

Creates **empty layouts** (cell positions across layers, NO tiles) → `NewLayout_<name>.json` (stones format), fed into **tile-level-design** which assigns tiles + scores difficulty.

**Layout = template (geometry only). Level = layout + tiles.**

---

## 1. READ EXPERIENCES.md FIRST

`EXPERIENCES.md` is the **token prior** — the learned NL experience library in the sense of Training-Free GRPO (arXiv 2510.08191). Claude (the frozen policy) reads it and CONDITIONS every layout generation on it. Do not generate without reading it.

Core rule from EXPERIENCES.md: **SPARSE-DEEP, never solid-shallow.** Real boards = small scattered base (~16 cells), towered ~6 layers, fill ~0.46 (NOT a solid blob).

---

## 2. Two generation modes

| Request | Mode | How |
|---|---|---|
| **A shape / prose** ("a sword", "a key", "this logo") | **compose** | Claude reads EXPERIENCES → designs [x,y,height] anchors → `claude_compose.compose(spec)` |
| **Bulk / abstract** ("100 layouts for the game") | **empirical** | `empirical_gen.sample()` — samples + perturbs real board skeletons from `templates_bank.json`; **7/8 KS-indistinguishable** from real |
| **Bulk, fully symmetric** ("100 đối xứng đẹp") | **symmetric** | exact h-symmetry **by construction** (symmetric-component crossover); fixes empirical's "gần đối xứng" jaggedness; offline via `symmetric_components.json` |
| **Bulk, real mix** ("100 khớp game, vừa sym vừa asym") | **mixed** | `~sym-frac` exact-symmetric + phần còn lại clean-asymmetric (drop trọn 1 cluster một bên, không lởm chởm) |

**Why Claude, not a parametric generator:** a hand-tuned parametric generator plateaus at ~1/8 KS match (features coupled). Sampling real skeletons hits 7/8 for bulk; and **only Claude** can make a recognizable novel shape in-distribution (e.g. a sword as diagonal/sparse/deep like the competitor's real level15 sword — a sampler cannot take "make a sword").

---

## 3. Compose mode — step by step

> **Recognizable shapes (icon/animal/logo)? Use the AESTHETIC path, NOT raw `compose()`.**
> `compose()` gives every base cell a lone +0.5 tower → the rim fringes into a checkerboard and
> the shape dissolves in the stacked render. Instead: build a 2D mask → **verify the FLAT
> silhouette reads** → `python ${CLAUDE_SKILL_DIR}/scripts/gen_shape_layout.py --mask m.txt --name duck --layers 5
> [--target 180]` (capped_inset depth: crisp rim + inset mound; emits `_<name>_flat.png` review +
> `_<name>_stack.png`). See EXPERIENCES [8]. Use bare `compose()` only for abstract/non-pictorial specs.

Claude authors the layout spec, code renders it:

```
Step 1. Read EXPERIENCES.md top to bottom.
Step 2. Design anchor list: [(x, y, height), ...] following every experience.
        - Sparse: ~8–16 base anchors, not a filled grid
        - Deep: heights 4–8 (mean ~5)
        - CLASSIFY symmetry FIRST (text prompts only; an image already carries it — B5):
          · Symmetric object (shield, heart, cup, lantern…) → build half + mirror=True
            (compose drops mirror-PAIRS → EXACTLY symmetric, no stray cells).
          · Elongated/asymmetric (sword, key, arrow, leaf…) → mirror=False + DIAGONAL tilt to one
            side (EXP [2]); a diagonal also fits the mobile-PORTRAIT frame — never lay it wide (B4).
Step 3. Run: python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode compose --spec '<JSON>' --name <name> --out <dir>
        e.g.: python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode compose \
              --spec '[[0,0,6],[1,2,5],[-1,3,4],[2,4,3]]' \
              --name sword --out layouts/
Step 4. Validate: check printed layout_diff (~5 target); inspect rendered PNG (optional).
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

## 4. Empirical (bulk) mode

Samples + perturbs real board skeletons. No LLM needed.

```bash
# 100 layouts matching real game distribution
python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode empirical --n 100 --out layouts/pool/ --seed 1

# Single abstract layout
python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode empirical --n 1 --out layouts/ --seed 42

# Abstract parametric families (more variety, lower KS match)
python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode abstract --n 50 --dmin 5 --dmax 8 --out layouts/

# FULLY symmetric (exact h-symmetry by construction; fixes empirical's "gần đối xứng")
python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode symmetric --n 100 --out layouts/sym_pool/ --seed 1

# Distribution-correct mix: ~64% exact-symmetric + ~36% clean-asymmetric
python ${CLAUDE_SKILL_DIR}/scripts/gen_layouts.py --mode mixed --n 100 --sym-frac 0.64 --out layouts/mix_pool/ --seed 1
```

Output: `NewLayout_<name>.json` + `manifest.json` per batch.

> **Why symmetric/mixed exist:** `empirical_gen` perturbs a real skeleton but its top-trim +
> support-cleanup are one-sided → only "gần đối xứng" (measured: 12% visibly asymmetric). `symmetric`
> and `mixed` delegate to `gen_symmetric.py` (component crossover) which guarantees exact h-symmetry
> by construction and runs **offline** via bundled `symmetric_components.json` (rebuild: `gen_symmetric.py
> --build-cache`; `--selftest` locks the math). See EXPERIENCES [12].

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
  "total_tiles":54,"capacity":18,"layout_difficulty":5.2}}
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

### 7b. Training-Free GRPO loop (optional, needs real boards data)

Run a GRPO round to update the experience library. **Free — no API.**

```bash
# Extract competitor boards first (one-time)
python -c "import zipfile; zipfile.ZipFile('refs/boards_Full.zip').extractall('data/boards')"

# Run 1 GRPO round (G=5 rollouts)
python ${CLAUDE_SKILL_DIR}/scripts/run_grpo_round.py --boards data/boards --G 5 --round 1 --save-dir data/grpo/

# Read the report, then Claude Code updates EXPERIENCES.md:
# - Which features was winner better at?
# - What structural pattern explains the gap?
# - Add/Modify/Delete/Keep in EXPERIENCES.md
```

**Loop:**
```
generate G layouts -> score vs real -> identify winner/loser -> Claude reads report ->
update EXPERIENCES.md -> generate G layouts again -> ...
```

Each round takes ~30s. Run 3-5 rounds per session. The paper uses 3 epochs; for our domain, 1-2 rounds per session is enough for a targeted improvement.

**When to update which experience:**
- Winner has feature X closer to real than loser -> reinforce the rule that drives X
- Loser keeps violating rule [N] -> strengthen rule [N] or add a clearer constraint
- Winner has a pattern not in EXPERIENCES -> Add new experience
- Two experiences say the same thing -> Merge them

---

## 8. Skill files

```
gen-layout/
  SKILL.md                  <- this file
  EXPERIENCES.md            <- token prior (12 learned rules, updatable)
  LAYOUT_PRIORS.md          <- statistical priors from 8019 real boards
  layout_priors.json        <- raw numbers
  templates_bank.json       <- 400 real board skeletons (for empirical_gen)
  engine/                   <- tile_level_simulator + verify_smart_v3 + solve_path + scoring_weights
  scripts/
    gen_layouts.py          <- CLI: --mode [empirical|abstract|compose|symmetric|mixed]
    gen_shape_layout.py     <- SHAPE layouts (icon/animal): mask -> capped_inset/even depth -> exact tile count [EXP 8,9]
    gen_region_depth.py     <- per-COLOUR-REGION depth from an image (beak/eye deeper than body) [EXP 10]
    gen_symmetric.py        <- FULLY-symmetric bulk gen via component crossover (--n / --selftest / --build-cache) [EXP 12]
    gen_soda_cup_cov.py     <- hit an exact cover100 % (e.g. 50/75% completely covered) via 2-phase tuner [EXP 11]
    run_grpo_round.py       <- TF-GRPO round runner (G rollouts -> KS score -> report)
    claude_compose.py       <- spec -> rendered cell-set
    empirical_gen.py        <- sample+perturb real skeletons (7/8 KS)
    validate_prior.py       <- KS reward function (full rigor, held-out test)
    validate_layout.py      <- structural validity check
    render_png.py           <- optional visualization
    clone_layout.py         <- copy + resize/reshape a reference board
    fit_layout.py           <- hit exact tile count target
    target_difficulty.py    <- hit level-difficulty target after tile assignment
    eda_full.py             <- EDA over a boards directory
    grpo_round.py           <- older parametric GRPO generator (kept for reference)
    test_full.py            <- test suite (12 tests)
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
