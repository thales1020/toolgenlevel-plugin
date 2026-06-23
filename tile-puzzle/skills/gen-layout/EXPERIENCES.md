# EXPERIENCES — token prior for layout generation (Training-Free GRPO)

This is the **experiential knowledge library** in the sense of Training-Free GRPO
(arXiv 2510.08191): a frozen LLM (**Claude is the generator/policy**) reads these
natural-language experiences and CONDITIONS its generation on them — no fine-tuning.

**How to use (Claude = the generator, NOT code):** when asked to generate a layout,
DO NOT default to a solid parametric silhouette. Generate the layout (cell-set or build
recipe) by FOLLOWING every experience below. Reward = match to the competitor distribution
(`validate_prior.py` KS + `empirical_gen.ENVELOPE`) + v3-solvable. Update this file via the
GRPO loop (`grpo_round.py`): generate → score → contrast winners/losers → Add/Modify/Merge/Delete.

Each entry: `[id] (option, refs) rule`. Learned by contrasting winner vs loser rollouts.

---

## Experiences

**[1]** (modify, round-7+9) **Build SPARSE-DEEP, never solid-shallow or over-fragmented.** A real board = a SMALL thin footprint (~16 base cells), MOSTLY single scattered cells (70% of base clusters are 1 cell), towered ~6 layers with **+0.5 diagonal stagger**. Total ≈72 cells, **n_clusters ~5–6 (CAP 12 — never above 12)**. Two failure modes: (a) solid silhouette (fill ~0.9, 1 cluster — R7 loser base_fill=0.944) and (b) over-fragmented (n_clusters=20 with cells=138 — R9 loser). Real boards are scattered BUT not atomized — 5–6 clusters of 2–4 cells each is the target.

**[2]** (add) **Recognizable / elongated shapes (sword, key, arrow, fish, leaf…) go DIAGONAL + sparse + deep.** Render the shape's PATH as a thin DIAGONAL line of sparse cells with a few crossbars, towered deep — NOT a solid vertical bar. Proof: the competitor's sword = 63 cells, **8 layers, diagonal**, scattered cells. A vertical solid sword (132 cells, 2 layers, aspect 0.47) is a LOSER; the diagonal sparse-deep sword (54 cells, aspect 0.85) is a WINNER. The shape reads from the sparse path + crossbars, not from fill.

**[3]** (modify, rounds 1+2+5) **Match these proportions — HARD FLOORS AND CAPS.** Held-out medians: width ~6 (4–9), height ~7 (4–10), **aspect w/h ~0.88**, **layers ~6 (FLOOR 4, CAP 8 — NEVER below 4 or above 8)**, **cells ~72 (range 40–100, NEVER above 100)**, capacity ~24, **base fill ~0.46**, **h-symmetry ~64%**. Evidence: R1 loser n_layers=10 → layout_diff=16 (cap violation); R2+R6 loser n_layers=3 → layout_diff too low (floor violation); R5 loser cells=141 → layout_diff=15 (cell cap violation, real p90=102). Build symmetric ≈2/3 of the time.

**[4]** (add) **Difficulty profile: deep-but-easy.** layout-difficulty ≈ 0.9 × layers (so ~6 layers → diff ~5–6). Cover ratio ~0.84 (most cells buried). ~12 cells pickable at start. This is ONLY achievable with sparse bases — solid bases at the same depth overshoot difficulty ~4×.

**[5]** (add) **Validity (hard).** Every cell at L>0 must OVERLAP ≥1 cell directly below (game cover rule, |dx|<1 & |dy|<1; corner contact at 0.25 area is OK — single-cell +0.5 towers are valid, don't require 0.5-area support). Total cells %3 == 0. Must pass v3-solvable.

**[6]** (modify, rounds 1+4) **Towers THIN but not TOO TALL — target tower_mean ~4 (range 3–5).** Use anchor heights **4–7 (a few at 3, most at 5–6)**; vary for thinning. HARD CONSTRAINT: mean tower height across all anchors MUST land 3–5 (target 4). R4 loser: tower_mean=11.79 (nearly every anchor reached near-max depth) → layout_diff=24 (5× overshoot). Vary heights so dense columns never form — if base has N anchors, expect tower_mean ≈ 0.65×max_height after variation.

**[7]** (add, from round-1) **Aspect: orient slightly TALL.** Round-1 symmetric scatter gave aspect 1.0 (real 0.88). Make the footprint ~1 row taller than wide (e.g. 6 wide × 7 tall) so aspect ≈0.88.

---

## Losers (anti-patterns — what to NOT generate)
- n_layers > 8 → tower_mean spirals → layout_diff overshoots 3×. [contradicts [3]]
- n_layers < 4 → layout_diff too low, board too shallow (R2, R6, R8). [contradicts [3]]
- tower_mean > 6 → layout_diff overshoots 5× even at moderate depth (R4/R10/R11). [contradicts [6]]
- cells > 100 → layout_diff overshoots (R5: 141→diff=15; R9: 138 + n_clusters=20). [contradicts [3]]
- n_clusters > 12 → over-fragmented base (R9 loser: 20 clusters). [contradicts [1]]
- base_fill > 0.7 → too dense / solid silhouette (R7 loser: fill=0.944). [contradicts [1]]
- Shallow 2-layer board → real is ~6 layers. [contradicts [1],[4]]
- Vertical thin bar for elongated shape → aspect ~0.5 (real 0.88). [contradicts [2]]
- Every layer = full base footprint → cells/difficulty overshoot. [contradicts [6]]

*Method: Training-Free GRPO. Claude = frozen generator conditioned on this library. Reward = KS-to-real + solvable. Iterate with `grpo_round.py`.*
