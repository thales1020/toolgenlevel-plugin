# LAYOUT_PRIORS — token prior for layout generation

**What this is.** A learned *token prior* (experiential knowledge `E`) in the sense of
Training-Free GRPO (arXiv 2510.08191): a frozen policy (Claude) is steered at inference by
injecting this knowledge into the generation context — no fine-tuning. It is distilled from
(a) EDA over **8019 real Tile Explorer boards** (the reward ground-truth), and (b) the
*semantic group advantage* of comparing our generated rollouts against that real distribution.

**How to use.** When generating layouts (single OR bulk), READ this file first and condition
choices (depth, base density, symmetry, difficulty) on it. When you discover a new lesson by
comparing generations to the real distribution, UPDATE the Experiences below (Add/Modify/Delete/Keep).

---

## A. Statistical priors (from EDA — `layout_priors.json`)

| Feature | Real distribution | Generator default should be |
|---|---|---|
| **layer_count** | peak **6** (4–8 span); 5=18%, 6=25%, 7=17% | ~6 layers, NOT 2–4 |
| **erosion** (layer size / base) | **~constant** 1.0–1.09, no taper | uniform_stagger ✓ (never pyramid) |
| **base (layer 0)** | median **16** cells | small base |
| **fill density** (base / bbox) | **0.46** (sparse/patterned) | NOT solid (≈1.0) |
| **cell_count** | median **72**, p90 102 (cap ~24) | ≲100 unless asked |
| **symmetry** | **h=64%**, v=44% | prefer horizontal symmetry |
| **aspect** (w/h) | **0.87** (slightly tall) | ~0.85–1.0 |
| **layout-difficulty** | median **~5**, p90 ~11, max ~31 | target ~5 by default |
| **base clusters** | median **5** components; largest = only **31%** of base; **90%** have ≥2 clusters | scattered, NO dominant blob |
| **diff vs depth** (real) | 3L→2.3 · 4L→3.4 · 5L→3.8 · 6L→**6.3** · 7L→7.4 · 8L→7.5 (≈ linear ~0.9/layer) | match this curve, not super-linear |
| **coverage** | 0%:18 · 25%:13 · 50%:20 · 75%:4 · 100%:46 | ~46% fully covered, ~18% pickable |

### Normal approximation (for QC acceptance bands — NOT for generation)
N(μ,σ) per metric — ~normal at **±2σ** (93–98% coverage ≈ 95.4%) but NOT truly Gaussian inside:
cell/capacity are **peaked + right-skewed** (skew +1.7, 81% in ±1σ, fat right tail of big boards),
width/height **slightly left-skewed**, base is **hard-bounded left → log-normal-like (skew +8.9, NOT normal)**.

| metric | μ | σ | μ±2σ (soft QC band) | shape |
|---|---|---|---|---|
| cell_count | 79.1 | 21.0 | 38–120 | right-skew (use p10/p90) |
| layer_count | 6.2 | 2.0 | 2–10 | ~normal |
| width | 6.3 | 1.1 | 4–9 | ~normal (best fit) |
| height | 7.1 | 1.4 | 4–10 | ~normal |
| capacity | 26.4 | 7.0 | 13–40 | right-skew |
| base | 17.8 | 10.6 | (−3)–39 → use p10/p90 7–30 | NOT normal |

Use μ±2σ (clamped ≥ valid min) as a soft "acceptable" QC band for width/height/layers; use empirical
p10/p90 for the skewed ones (cell/capacity/base). Full numbers in `layout_priors.json` → `normal_approx`.

**This IS wired as a generation ENVELOPE** (`empirical_gen.ENVELOPE`): generated layouts outside the
band are rejected + resampled — **±2σ for width/height/layers** (≈ normal), **empirical bounds for
cells/base** (±2σ would chop the real right tail / go negative). Verified: envelope keeps KS at 7/8
match and nudged `cells` tell→close, with no yield loss (10/10 in 13 attempts).

## B. Experiences (semantic advantage — the actual learned rules)

1. **DEEP is normal.** Real boards are ~6 layers, not shallow. Default depth ≈6 (range 4–8). A 2-layer board is an outlier (lowest reward in every rollout group).

2. **Layers do NOT taper.** Per-layer size stays ~constant (ratio ~1.0). `uniform_stagger` matches this exactly; the old full-pyramid (erode-to-mound) is WRONG and off-distribution. Keep using uniform_stagger.

3. **⭐ The "deep-but-easy" rule — VERIFIED.** Real boards are **6 layers YET layout-difficulty only ~6.3**, growing ~LINEARLY (~0.9/layer). Falsifiable check (`verify_priors.py`, depth 6): REAL=6.3, **SOLID-gen=26.7** (off +20.4), **SPARSE-gen=11.3** (off +5.0) → solid overshoots ~4×, sparse ~2×; sparse tracks real, solid does NOT. The cause: real bases are **scattered (median 5 clusters, no blob >31%)**, keeping per-cell coverage low even when stacked deep. → Generate **scattered/sparse cell clusters, NOT solid silhouettes**. (Confirmed: real board_0397 = 7 layers, diff 6.0, renders as scattered clusters.)

4. **Sparse bases win.** In rollout groups, `punch_holes`/`jitter`/`ring`/`plus` (fill ~0.48–0.52) beat solid `square`/`circle` (fill ~0.75–0.97). Bias toward holed/sparse/patterned bases; fill density target ≈0.46.

5. **Horizontal symmetry pays.** 64% of real boards are h-symmetric. `mirror_h` (or h-symmetric families) consistently scored higher. Prefer it; vertical symmetry is secondary (44%).

6. **Keep it small.** Median 72 cells (cap ~24). Don't ship 300–600-cell monsters by default (our d6-8 batch overshot size because solid shapes at depth blow up cell count).

7. **Difficulty centers low.** Most real boards are Easy–Normal *geometry* (diff ~5). Only target high layout-diff when explicitly asked; default to ~5.

## C. Generator status — CALIBRATED ✅ (`real_match` family)
The `real_match` family (`shape_factory.spaced_clusters`, small 3×4-slot canvas, 2×2 blocks,
h-symmetric) built with **`LB.build(grid, keep_upper=0.9)`** now MATCHES the real difficulty
curve. Calibration (`calibrate_sparse.py`) result: diff-by-depth **{4:3.8, 6:6.2, 8:8.1}** vs
real **{3.4, 6.3, 7.5}** → **meanErr 0.38** (was 5.0 for solid, 1.87 for naive sparse). At the
median depth 6 it is 6.2 vs real 6.3 — essentially exact. Cell count ~66–92 (real median 72) ✓.
Two levers found: (1) **separated 2×2 clusters** (cross-cluster gaps don't matter — vertical
towers drive resolve); (2) **`keep_upper=0.9`** thins upper layers so towers vary in height →
resolve stays ~linear in depth like real (instead of super-linear). Cross-validation: the config
that matched the difficulty curve also lands on a scattered cluster layout that renders like real
boards (e.g. board_0397). To generate real-matching layouts: `real_match` family + keep_upper=0.9,
depth ~6. (Solid families remain for ARTISTIC/recognizable shapes — different goal.)

## C2. RIGOROUS distribution validation (`validate_prior.py`) + `real_gen`
Upgraded the method to "chuẩn": **dedup the corpus (35.5% exact dups removed!)** → **held-out TEST set** → **KS 2-sample test per feature** (GEN vs held-out real). The canonical generator is `real_gen.py` (probabilistic symmetry 64%, wide randomized params for variety, calibrated over 5 GRPO passes: gen→measure-KS→adjust→repeat).

**HAND-TUNED PARAMETRIC GENERATOR PLATEAUED at 4/8** over ~8 passes — features are coupled
(fixing cells breaks n_clusters), so a code generator modeling the joint with gauss params
cannot close all 8. Per the Claude-vs-Code split, the un-adaptable GENERATION step was MOVED
off hand-params onto **data sampling** (`empirical_gen.py` + `templates_bank.json` = 400 real
board cell-sets, abstract coords only — no tiles/theme). It samples a real skeleton and perturbs
it (gentle top-trim, symmetric-pair drop, mirror) with a support-cleanup so every output is
structurally valid; this matches the real JOINT distribution by construction.

**FINAL KS (held-out, dedup'd, crit@p=0.05 = 0.122): 7/8 INDISTINGUISHABLE** —
base_fill 0.048, aspect 0.056, sym_h 0.057, layout_diff 0.063, n_layers 0.065, n_clusters 0.070,
tower_mean 0.105 — **+ 1 modest tell** (cells: gen ~69 vs real 72, KS 0.26, ~4% off median).
Output is structural 10/10 + v3-solvable 10/10. This is the production default in `gen_layouts`
(`--abstract` reverts to the parametric families). Honest: 7/8 indistinguishable on held-out is
strong but NOT "certified identical" — `cells` is still a slight tell, bounded by the support-
cleanup that guarantees validity. Lesson: hand-tuned params hit 4/8; sampling-from-data hit 7/8.

## D. Verification (falsifiable — `verify_priors.py`)
- **CHECK 1 — parsing**: computed layer_count/cell_count vs each board's OWN stored fields → **99.8% match** (n=2653). Pipeline reads boards correctly. PASS.
- **CHECK 2 — deep-but-easy**: diff-by-depth REAL vs SOLID vs SPARSE → solid overshoots ~4×, sparse ~2×, sparse tracks real. **PASS** (claim supported; generator not yet fully calibrated).
- Core knowledge VERIFIED; the open item is generator calibration, not the priors themselves.

---
*Method: Training-Free GRPO (Tencent Youtu, arXiv 2510.08191). Reward = match-to-real (`tfgrpo_priors.py`). Corpus: `refs/boards_Full.zip` (8019 non-empty boards). Re-run: `eda_boards.py` (priors), `eda_structure.py` (clusters/depth), `verify_priors.py` (falsifiable checks).*
