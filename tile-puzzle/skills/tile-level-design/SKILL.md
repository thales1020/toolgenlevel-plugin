---
name: tile-level-design
description: "Design, generate, analyze, and modify Triple Match LEVELS in the Tile Explorer (GD_Test) simulator: assign tiles, score/analyze difficulty (5-component), solve/verify (DFS v3), build trap / difficulty-targeted / easy-layer / bridge levels (single or in bulk), make a level easier/harder, and normalize level files. Ships 120 sample layouts, so it can produce a complete level even when none is given; also accepts a layout (e.g. NewLayout_*.json from gen-layout). Does NOT design new layout geometry/shapes."
when_to_use: "When the user wants to make/generate a level (one or many), assign tiles, hit a target score/difficulty, verify/solve, build trap/easy-layer/bridge levels, analyze or score an existing level, make a level easier/harder, or normalize a level file — with or without a given layout. For a level FROM AN IMAGE/SHAPE, the gen-layout skill runs first to build geometry, then this skill assigns tiles (e.g. to hit a cover100/coverage or difficulty target). Does NOT create empty layout shapes — that is gen-layout."
---

# Tile Level Design Skill (compressed)

## 1. CRITICAL invariants

1. **Game-over**: `tray_size >= 7 AND no triple` (NOT `> 7`)
2. **Display labels**: `tile_id + 1` (UI 1-indexed, internal 0-indexed)
3. **Atomic triple bounds**: `cur_tsize + (needed-1) < 7` mid-batch
4. **Layout capacity**: `total_cells // 3` — skip if requested > cap
5. **Use `load_board_from_file`** with absolute path
6. **`eng.validate = False`** for fast generation
7. **"Easy layer" def (hard requirement)**: a layer is "easy" only if `max_tray_size_during_clear <= 5` on the actual v3 pick sequence (tray never hits ≥6) — STRICTER than the game-over ceiling of 7. Verify the ≤5 ceiling on the replay, not on static distribution. Use for any "top N layers easy" ask.

## 2. Solvers

- `verify_smart_v3.solve_v3(board, max_expansions=N)` — DFS, returns `(True/False/None, depth, exp)`
- `solve_path.solve_with_path(board, N)` — same DFS + records picks
- `count_solutions.py` — exact count of distinct winning paths (memoized DP, ~15s for 69-cell boards; counts commonly 10³⁰⁺ — too big to discriminate, use only when literally asked "how many solutions")
- v3 cap **100k** for general use, **50k** for sweeps (90% solvable boards solve <50k)
- NEVER use stock `TileSolver.analyze` (hardcoded 500-cap MC, unreliable)

## 3. Scoring formula

### 3.0. `new_diffScore` — RANK LEVELS WITH THIS ⭐ (real-play validated)

The recommended player-difficulty metric. STATIC board formula, fit + validated on ~55K real plays of
the live Pyramid game (LOO-CV Spearman **0.615** all / **0.732** plain-only — see docs/HANDOFF_KNOWLEDGE.md §4.3).

```
new_diffScore = max(0, -28.42 + 0.655·intra_group + 0.804·cover100 + 2.897·n_types + 22.76·is_mystery)
```
- `intra_group`, `cover100` — from `DifficultyScorer.compute_full_score` (the two chaos-score components
  that actually track difficulty; they feed THIS — don't rank with `final_score`).
- `n_types` — distinct `tile_id` over all cells. `is_mystery` — 1 if any stone is mystery (`o:[0]` or legacy `m:true`).
- Tool: `scripts/diff_score.py <level.json>` (or `analyze_level.py` now prints it first).

| new_diffScore | Tier (relative guide) |
|---|---|
| < 20 | Easy |
| 20 – 35 | Normal |
| 35 – 50 | Hard |
| 50 – 65 | Very Hard |
| ≥ 65 | Extreme |

**Known limitation:** static-only, BLIND to in-level mechanics → it **always UNDER-rates** hard mechanic
levels (never over-rates), EXCEPT the `+22.76` mystery term which **OVER-rates** already-easy mystery
boards. Board-only ceiling ≈ 0.63–0.66; treat tiers as a relative guide. Don't sprinkle Mystery casually.

### 3.1. `final_score` — OLD chaos-score (visual complexity, NOT for player-difficulty)

DEPRECATED for ranking — it measures visual chaos, not difficulty (it UNDER-rates traps and INVERTS on
bridge tiers). Kept only as a feature (its `intra_group`+`cover100` feed `new_diffScore`) and for
score-band screening during generation.

```
final = layout × 0.3 + inter × 0.3 + intra × 1.0 + cover100 × 0.6 + pick_div × 0.5 
        (X=0.3)        (Y=0.3)       (Z=1.0)       (K=0.6)         (D=0.5)
```
All weights in `scoring_weights.json` 1:1 — no hardcoded multipliers.

`DifficultyScorer.compute_full_score(board, weights)` returns a dict: component scalars (`layout`
`inter_group` `intra_group` floats; `cover100` `pickable_diversity` `stripped` `remaining_tiles` ints),
`final_score` (float), **and `weights` (a nested DICT)**. Use `['final_score']`; never `round()` the
whole dict (the `weights` value is a dict → TypeError — BUGLOG B1). To gen a quick spread of solvable
levels, RUN `templates/gen_test_set.py [N]` rather than hand-writing a loop.

**Difficulty tier thresholds** (recalibrated for the 5-component formula — how to interpret a `final_score`):

| Tier | final_score |
|---|---|
| Very Easy | < 5 |
| Easy | 5 – 25 |
| Normal | 25 – 55 |
| Hard | 55 – 85 |
| Very Hard | 85 – 120 |
| Extreme | ≥ 120 |

Median solvable score ≈ 11 (from 4964 samples); max ever ≈ 190 (L109, deep). NOTE: the engine's stock `_complexity_label` thresholds are STALE (designed for 0–100; score now reaches ~190) — use THIS table, not the engine label. Old "Z=0.5" scores read ~2× lower; deep-layout max went ~120 → ~200 after the overhaul.

| Component | Computed on | Logic |
|---|---|---|
| **layout** | Full board, physical layer | BFS resolve count |
| **inter_group** | Active sum effective_score per type avg | Variety across types |
| **intra_group** | Active per-type spread (max-min)/count | Spread within type |
| **cover100** | Active sum, area-based ≥90% | Cells with ≥90% surface covered (`VISUAL_TILE_SIZE=1.0`) |
| **pickable_diversity** | Active set | # distinct types in pickable cells (loose start = high) |

**Strip easy triples** (mô phỏng player clear easy):
- 2-layer window uses **effective_layer** (`#higher_layers_with_overlap + 1`)
- Same-type subtract = -1 (NOT -N) — hidden tiles aren't "easy" from player view

## 4. Six design patterns

| # | Pattern | Method | Template |
|---|---|---|---|
| 1 | **Trap ẩn / 90% fail** | TEEngine + greedy fail ≥0.90 | `find_trap_fast.py` |
| 2 | **Top N layers dễ** | TEEngine + window metric | `find_easy_first_half.py` |
| 3 | **Easy top + trap bottom** | Custom + bridge | `find_bridge_L21.py` |
| 4 | **Clear 50% rồi bí** | Custom + auto-strategy | `find_clear50_trap.py` ⭐ |
| 5 | **Guided Trap** | 3-zone gradient + breadcrumbs | `find_guided_trap_L21.py` |
| 6 | **Score X solvable** | Inline TEEngine + filter | inline (no template) |

**Decision tree**:
- "trap ẩn / cần booster" → P1
- "top dễ" → P2
- "dễ đầu khó cuối" → P3
- "clear 50% rồi bí" → P4
- "guided / breadcrumbs" → P5
- "score X solvable + layout Y" → P6 (inline, fastest)

## 5. Three assignment strategies

| Strategy | Layout type | Templates |
|---|---|---|
| **Random** | Single pickable layer (24 layouts) | `find_hybrid_fast.py` |
| **Priority** | Pickable trải 2+ layers (74 layouts) | `find_hybrid_priority_v2.py` |
| **Cascade** | Top-only pickable + uniform deep (19 layouts) | `find_hybrid_cascade_L21.py` |

**Cover100 % rule**:
- < 50% → any strategy
- 50-70% → Random/Priority OK
- **> 70% → CHỈ Cascade/Bridge/Guided** (Random fail 510x slower)

Reference: `layout_strategy_analysis.csv` (117 layouts classified).

## 6. Bridge Distribution (4 type groups)

| Group | Copies | Placement |
|---|---|---|
| Easy-only | 3x | Top layer only |
| **Bridge** | 6x | 1/layer top→bottom (sparse) |
| Hard-mid | 6x | L3+L2 concentrated |
| Trap-only | 3x | Bottom only |

**Critical**: Bridge phải span BOTH top AND bottom + form matchable triples khi reveal. Top layers ≥2 instant triples.

## 7. Speed optimization (cũ → 90x speedup)

1. **Filter order**: type → score → v3(100k) → greedy(30) → greedy(300)
2. **Precompute bb[] once** (layout-only)
3. **Clone in-memory** (không reload disk per iteration) — 2260x speedup on `find_hybrid_custom.py`
4. **2-stage greedy**: 30 quick → 300 full (chỉ promising)
5. **Unique output files** per worker: `*_s{seed}.json`
6. **8 parallel workers** — canonical fixed seed set `1 11 23 47 101 239 991 1001` (spreads RNG, no collisions). Shell fork: `for seed in 1 11 23 47 101 239 991 1001; do python find_*.py $seed & done`. (Hard requirement from docs/CLAUDE.md.)
7. **Early termination**: skip remaining samples if N consecutive fail

**Engine DIFFICULTY_PRESETS** (param sets by level-number, in `engine/`): Tutorial 1-50 cc=3 · Mid-game 51-100 cc=4 +up_easy +val_replace · Hard 101-500 cc=5 hard_code=1 distance=3 · Very Hard 500+ cc=6 hard_code=2 distance=5 · Extreme cc=7 hard_code=3 distance=8. (This is GEN params by level #, NOT the score-tier table in §3.)

**Benchmarks**:
- 9 templates parallel: 30 phút → **20s** (gen_all_9.py)
- Solvable sweep 117 layouts: 17 hours → **39 phút** (parallel + v3 cap 50k + early term)

## 8. Reference CSVs

| File | Content |
|---|---|
| `difficulty_minmax_combined.csv` | **2265 rows, 20 cols** — solvable only with component breakdown (latest) |
| `layout_strategy_analysis.csv` | 117 layouts: pickable/cover100/stacks/strategy |
| `scoring_weights.json` | X=0.3 Y=0.3 Z=1.0 K=0.6 D=0.5 (clean 1:1, no hardcoded mult) |

**CSV columns** (20):
```
layout, tile_count, total_cells, capacity,
score_min, score_max, method_min, method_max, n_solvable, n_total,
min_layout, min_inter, min_intra, min_cover100, min_pickdiv,
max_layout, max_inter, max_intra, max_cover100, max_pickdiv
```

## 9. Score range thực tế (sau formula mới + solvable only)

| Layout | Cells | Layers | Max solvable score |
|---|---|---|---|
| L60 | 66 | 3 | ~52 |
| L59 | 72 | 4 | ~87 |
| L62 | 87 | 7 | ~126 |
| L109 | 126 | 10 | ~190 (highest) |
| L14, L54 | 120 | 6 | ~170 |

**Tile count tối ưu cho hard-but-solvable**: ~70-80% capacity. Trên 80% → solvability rate <30%.

## 10. PlayWindow UI (modified)

- **Tile icons** (Unicode symbols): ★♥♦♣♠✿❀☀☂☃⚓⚡✈✚✪❄✦❁♛♞♫✓✶❖♨ (25 types)
- **Font**: Segoe UI Symbol, size 28×zoom (min 18)
- **Tile rect**: 36×zoom×1.0 (full grid, match game visual)
- **Coords toggle button**: ON/OFF for `L0(x,y)` labels
- **Buffs modified**:
  - Shuffle: dynamic 2-3 triples + tray priority (types on tray > types off tray)
  - Undo: 1 tile (was 3)
  - +1 Slot: tray 7→8 once
- **Restart safe**: `_original_tile_ids` saved at init

**Two ways to PLAY a level**:
- `scripts/open_any_level.py <level.json>` — tkinter desktop window. **Local only** (Claude Code/VS Code); needs a display. Does NOT work on claude.ai web sandbox.
- `scripts/make_play_html.py <level.json> [out.html]` — generates a self-contained playable HTML (faithful rules: pickable=no higher-layer overlap, tray≥7+no-triple=game-over, win=cleared, +Shuffle/Undo/+1Slot buffs). **Works EVERYWHERE incl. web** — sandbox writes the file, user downloads + opens in any browser. Shareable single file. Use this on claude.ai web.

## 11. Standard workflow

1. Parse: score X, layout Y, constraints
2. Check `difficulty_minmax_combined.csv` for feasibility
3. Pick pattern (1-6) → template
4. **Inline gen** if pattern 6 (just score + solvable) — fastest
5. Else launch 8 workers with `find_*.py`
6. Verify v3 + save unique JSON before play
7. `mcp__tile-sim__play_level` to test

## 12. User phrase mapping

| User says | Pattern | Action |
|---|---|---|
| "trap ẩn / cần booster" | P1 | `find_trap_fast.py` |
| "top dễ" | P2 | `find_easy_first_half.py` |
| "dễ đầu khó cuối" | P3 | `find_bridge_L21.py` |
| "clear 50% rồi bí" | P4 | `find_clear50_trap.py` |
| "guided / không đoán mò" | P5 | `find_guided_trap_L21.py` |
| **"score X + layout Y + solvable"** | **P6** | **inline TEEngine** (fastest, ~1-30s) |
| "tạo 9 levels" | All | `gen_all_9.py` (~20s) |
| **"N màn test / test set / nhiều màn"** | - | **`gen_test_set.py [N]`** (~2s, spread band, v3-verified) |
| "min/max sweep" | - | `difficulty_minmax_solvable_parallel.py` (~40min) |

## 13. Bug avoidance

- [ ] Game-over check `>=7 AND no triple`
- [ ] Display labels `tile_id + 1`
- [ ] Save unique JSON before play_level (workers race)
- [ ] v3 + solve_path double-verify
- [ ] Cover100 area-based with VISUAL_TILE_SIZE=1.0

## 14. Time-wasters (skip these)

- TileSolver.analyze (500-cap MC, wrong)
- Score thresholds from old CSV (need ×1.7-2 recalibration with new formula)
- Single-worker for score sweeps
- Templates with hardcoded score targets (use new range from CSV)
- Random pool on cover100 >70% layouts (510x slower)

## 15. ALWAYS-solvable rule (non-negotiable)

Every level delivered to the user MUST pass `verify_smart_v3.solve_v3(board) == True`.
- `None` (cap hit) is NOT acceptable for delivery — bump cap (200k → 2M) until definitive `True`, or regenerate.
- `None` only OK while *screening* candidates mid-search.
- Applies to ALL gen paths including P6 inline — never skip v3 just because it's fast.
- If a constraint can only produce unsolvable boards, report that back; don't ship `False`/`None`.
- Caveat: v3 = tray-7 hard ceiling, no buffs. "Solvable" = solvable without Shuffle/Undo/+1Slot (strictest bar).

**⚠️ Inline P6 default is EASY**: "gen any solvable level" with no difficulty/pattern stated → low color_count + low distance → trivially easy (score ~0.7–5 measured across L10/25/40/60/86). For a real difficulty, the user MUST state a target score or pattern; then loop seeds filtering on score range, not just solvability.

## 16. Normalize workflow (saved-JSON → game-ready)

To standardize any saved level JSON to the canonical format:
1. `scripts/analyze_level.py <file> [--save]` — reverse-computes layout/difficulty/5-components/type_dist, injects `metadata` block.
2. Drop legacy `dif` field; preserve game fields (`group/bg/bgm/sl/stacks`).
3. Minify: `json.dump(data, f, separators=(",",":"), ensure_ascii=False)`.
4. `scripts/batch_normalize.py` for bulk (edit `LEVELS` list).
5. Empty/test layouts (no tiles) → `difficulty:null`, `capacity = total_cells // 3`.

## 17. Bridge difficulty variants (quick table)

| Variant | Bridge types | L1 copies/type | L3 content | Score |
|---|---|---|---|---|
| Easy | 4 | 3 (match ngay) | easy + bridge | ~71 |
| Harder | 4 | 2 (cần L0 thứ 3) | easy + bridge | ~67 |
| Hard | 2 | 1 (rải xa) | hard_mid trap | ~58 |

**Hard variant** inherently ~17min (fail≥95% + 2 types — search space cực hẹp, đừng parallelize). No bundled script — derive from `find_bridge_L21.py` with a Hard-variant score filter (see caveat below).

**⚠️ Known caveat (reconstruction)**: `find_bridge_L21.py` and `find_hybrid_fast.py` are faithful RE-CONSTRUCTIONS (the originals existed only on a prior machine). They produce valid v3-solvable bridge/hybrid levels, but the score targets above (~71/67/58) are NOT yet guaranteed — first-solvable hit on seed 1 often lands ~34. To hit a target score, remove the early-exit and add a per-variant score filter, or run more seeds. Only `find_trap_fast.py` is verified byte-exact to the original.

## 18. Detailed reference docs (read on demand)

The `reference/` folder next to this SKILL.md holds 16 distilled experience docs. Read the relevant one when going deep:

| File | When to read |
|---|---|
| `game_rules_and_bugs.md` | Before writing ANY solver/replay — the bug-causing invariants |
| `solver_infrastructure.md` | Which solver for what (v3 / solve_path / count_solutions) |
| `effective_layer_concept.md` | Understanding cover100 + strip 2-window mechanics |
| `level_design_patterns.md` | Full 6-pattern catalog with method + template |
| `layout_strategy_mapping.md` | 117 layouts → Cascade/Priority/Random classification |
| `bridge_distribution.md` | Bridge 4-group design (easy/bridge/mid/trap) |
| `guided_trap.md` | 3-zone gradient + breadcrumbs detail |
| `cascade_assignment.md` | Vertical-stack reveals for deep uniform layouts (L21) |
| `hybrid_easy_top_trap.md` | Custom assignment bypassing TEEngine |
| `hidden_trap_levels.md` | Trap ẩn design (v3-solvable + 95-100% greedy fail) |
| `feedback_search_speed.md` | 8 speed rules + benchmarks (1130s→0.5s) |
| `feedback_priority_assignment.md` | Easy on pickable cells, not cover100 |
| `feedback_verify_before_play.md` | Save unique JSON before play (worker race) |
| `t3_cover100_pitfall.md` | Why Random fails 510x on cover100>70% |
| `gen_all_9_pattern.md` | gen_all_9.py parallel batch internals |
| `difficulty_design_workflow.md` | Distribution-based metrics + 8-worker approach |

`INDEX.md` = original index of these (point-in-time snapshot).

## 19. Skill is self-contained — all paths relative to this SKILL.md

This skill bundles everything needed to RUN, not just guidance. Layout (relative to the skill's base dir):
```
SKILL.md
reference/        — 16 distilled experience docs (read on demand) + INDEX.md
engine/           — tile_level_simulator.py + verify_smart_v3.py + solve_path.py + scoring_weights.json
templates/        — find_*.py + gen_*.py (22 gen/sweep scripts)
sample_layouts/   — 120 empty layout JSON (NewLayout_L3..L120 + Clover/SKY/Smiley)
scripts/          — analyze_level.py, batch_normalize.py, open_any_level.py, export_trap.py,
                    reserve_special.py, solve_special.py, add_special_cells.py, export_game_format.py (special cells §23)
data/             — difficulty_minmax*.csv, layout_strategy_analysis.csv
docs/             — CLAUDE.md (hard reqs), LEVEL_DESIGN_GUIDE.md
example_levels/   — reference good levels (trap_an_L20_s82, etc.)
```
**Portability**: scripts + templates auto-locate `engine/` and `sample_layouts/` relative to the skill root, so the whole skill folder runs anywhere it's copied — no external project needed. Output levels go to a `levels/` dir in your current working directory (pass as arg).

**Invocation paths** — use `${CLAUDE_SKILL_DIR}` so scripts resolve regardless of cwd (D5):
```bash
python ${CLAUDE_SKILL_DIR}/scripts/analyze_level.py <level.json> [--save]
python ${CLAUDE_SKILL_DIR}/templates/find_trap_fast.py <seed> <layout> <smin> <smax> <tmin> <tmax>
python ${CLAUDE_SKILL_DIR}/scripts/open_any_level.py <level.json>
```
`${CLAUDE_SKILL_DIR}` expands to the skill's own directory (`.claude/skills/tile-level-design` at project scope).

## 20. Worked examples (few-shot)

Concrete end-to-end runs. Patterns to copy, not just describe.

### Ex 1 — "Tạo level trap ẩn" (P1)

```python
# Single-worker often enough; seed 1 hit in 4.7s. Template handles type→score→v3→greedy filter.
# templates/find_trap_fast.py  <seed> <layout> <score_min> <score_max> <types_min> <types_max>
python ${CLAUDE_SKILL_DIR}/templates/find_trap_fast.py 1 L20 65 90 15 22
# -> [84] s=84.4 t=15 fail=100%  SAVED trap_L20_candidate.json
```
Then ALWAYS verify + export (don't ship the raw candidate):
```python
board = rebuild_from_candidate(...)          # Board from layers
res, depth, exp = solve_v3(board, 100_000)   # must be True (rule §15)
res2, picks, _, _ = solve_with_path(board, 200_000)   # double-verify + get picks
# export stones-format minified, inject metadata, save to levels/
```
Result was: L20, 15 types (9×6 + 6×3), score 84.36, v3 depth=72 exp=231, greedy fail 100%. Hidden trap = solvable but every naive path dies.

### Ex 2 — "Score ~50, layout L25, solvable" (P6 inline, fastest)

No template — inline TEEngine, loop seeds until v3=True, confirm at 2M cap:
```python
for seed in range(1, 50):
    random.seed(seed)
    board = load_board_from_file(abs_path('sample_layouts/NewLayout_L25.json'))
    for c in board.all_cells(): c.tile_id = -1     # reset stale (core_invariants)
    eng = TEEngine(); eng.validate = False
    eng.color_count = random.choice([6,8,10,12]); eng.hard_code = ...; eng.distance = ...
    eng.generate(board)
    score = DifficultyScorer.compute_full_score(board, weights)['final_score']
    if solve_v3(board, 200_000)[0] is True:        # screening
        if solve_v3(board, 2_000_000)[0] is True:  # definitive (rule §15)
            break
```
Hit seed 1 instantly: L25, 75 cells, 9 types, score 49.6, v3 depth=75 exp=79.

### Ex 3 — "Chấm điểm level này" (analyze)

```bash
python ${CLAUDE_SKILL_DIR}/scripts/analyze_level.py levels/trap_an_L20_s1.json          # print only
python ${CLAUDE_SKILL_DIR}/scripts/analyze_level.py levels/trap_an_L20_s1.json --save   # + inject metadata
# -> Layout L20 (via position-signature match), diff 84.36,
#    layout=6.93 inter=87.83 intra=36.33 cover100=26 pickdiv=8
```
Layout auto-detected by `(layer_idx,x,y)` signature — works across theme variants (ignores tile_id).

### Ex 4 — "Check level có giải được không" (v3, cap escalation)

```python
res, depth, exp = solve_v3(board, 200_000)
# res=None, exp=200000 (hit cap) -> INCONCLUSIVE, escalate:
res, depth, exp = solve_v3(board, 2_000_000)
# res=False, exp=806137 (< cap) -> PROVEN unsolvable (search exhausted under cap)
```
Decision rule: `False` + `exp < cap` = proven unsolvable. `None` = hit cap, must bump. `True` = solvable. (Real case: L300, 93 cells all types ÷3, deadlocks at depth 18/31.)

### Ex 5 — "Chuẩn hóa file NewLayout này" (normalize)

The most common normalize case: a raw `NewLayout_*.json` with legacy `"dif":1` and no metadata.

**Before** (`NewLayout_L3.json` as shipped):
```json
{"group":1,"tiles":"","layers":[{"index":0,"stones":[{"i":2,"x":-2.0,"y":3.5}, ...]}, ...],"stacks":[],"dif":1}
```
**After** (`scripts/batch_normalize.py`, or `analyze_level.py <f> --save`):
```json
{"group":1,"tiles":"","layers":[...],"stacks":[],"metadata":{
  "layout":"L3","n_layers":2,"n_types":12,"total_tiles":48,"difficulty":0.31,
  "score_components":{"layout":1.04,"inter_group":0.0,"intra_group":0.0,"cover100":0,"pickable_diversity":0},
  "type_distribution":{"2":3,"3":6,...}}}
```
Transform rules:
- **Drop** legacy `"dif"`; **add** `metadata` block (extra top-level fields are ignored by the game loader — safe to ship).
- Coords → floats not strings (`"x":"-1.5"` → `-1.5`); empty cells get `"i":0`.
- **Preserve** game fields: `group / bg / bgm / sl / stacks`.
- `metadata.layout` = position-signature match in `sample_layouts/`, else filename.
- Empty/test templates (no tiles) → `difficulty:null`, `capacity = total_cells // 3`.
- Bulk: edit the `LEVELS` list in `batch_normalize.py`. Batch run on NewLayout_L3..L20 surfaced the tier spread: 5 Very-Easy (L3/L4/L8/L10/L13, all 4 components=0 after strip), up to L12 Hard (66.2, 9 layers).

### Ex 6 — "Tạo 9 levels demo" (batch)

```bash
python ${CLAUDE_SKILL_DIR}/templates/gen_all_9.py    # 7 subprocess + 2 inline -> all_9_boards.json ~20s
```
Each of the 9 is independently v3-verified inside the script before saving.

## 21. Quick-facts (knobs · partition math · metrics · relaxation)

Decision-critical reference (full detail in `docs/CLAUDE.md` + `docs/LEVEL_DESIGN_GUIDE.md`).

**TEEngine knobs** (the levers to hit a target difficulty):
| Knob | Effect |
|---|---|
| `color_count` | 2–25 types (game 2–9; 10–25 tool-only). More types → harder |
| `hard_code` | 0–3; adds extra color types |
| `distance` | 0–15; spreads same-type farther apart → harder |
| `up_easy` / `top2_easy` / `top3_easy` / `top4_easy` | Top N layers get only easy (low-count) types |
| `less_type` | Reduce type variety in middle layers |
| `val_replace` / `val_mode` | Value-replace post-process (level 51+) |

**Custom-assignment partition math** (general, not just bridge): `x types × 6 + y types × 3 = total_cells`. Worked: L20 7×6+10×3=72 (17 types) · L21 4×6+14×3=66 (18) · L25 8×6+9×3=75 (17) · L74 6×6+11×3=69 (17).

**Layout-pool depth math** (for "top N easy" asks): deep 5-7 layer (L50/L115) top-3 ≈ 18 cells → max 6 triple-ready types. 4-layer (L86/L70/L18) top-3 ≈ 50-60 cells → 10-15 types. 3-layer = 100% top-3 but no depth score.

**Metric thresholds** (empirically tuned):
- 2-adjacent-layer window: type "easy" if ≥3 copies in window; "top N easy" fraction threshold ≈ **0.85** (or ≥0.60 looser).
- Deadlock proof (unsolvable): v3 to exhaustion, accept only if `visited < beam_width` AND `best_depth ≥ frac × total_cells`.
- Random-playout fail-rate: require `fail_rate ≥ 0.80` AND v3 confirms ≥1 solution; trust only at 80%+.
- Tray-pressure profile is UNRELIABLE for easy→hard (v3 atomic path keeps tray flat ~6) — don't use it.

**Relaxation order when no candidate matches**: widen score range FIRST → then top-3 thresholds (max_types 5→8, triple_frac 0.90→0.85) → NEVER silently relax the user's explicit tile-count range. Keep a `best` tracker for best-effort fallback.

**Capacity ceilings**: layout capacity = `total_cells // 3`. Custom-assignment v3 pass rate ~3% (vs TEEngine ~0.2% same constraints). Hard-but-solvable sweet spot ≈ 70-80% capacity; >80% → solvability <30%.

## 22. Pipeline: image/shape → playable LEVEL (cross-skill)

A request like *"a level from this image, 50% of tiles 100%-covered, difficulty = X"* spans BOTH the
**gen-layout** skill (builds geometry) and this one (assigns tiles). **Claude (main loop) orchestrates —
skills do NOT call each other**; the hand-off is the `NewLayout_*.json` file.

1. **Order**: gen-layout builds geometry from the image → `NewLayout_*.json` → this skill assigns tiles.
2. **Geometry sets the ceiling**: layout depth/cells cap achievable difficulty AND cover100 (a shallow shape caps the score low — see §9); tiles dial only WITHIN it.
3. **Coupling**: cover100 is a score component (K=0.6), so a coverage target and a difficulty target are NOT independent — solve them together.
4. **Auto-retry (silent)**: target missed but feasible → regenerate deeper / more seeds before asking the user.
5. **Conflict → ask the user**: PROVEN mutually-infeasible constraints → do NOT silently relax (§21) and do NOT ship a bad board (§15). Diagnose quantitatively (which constraints clash, achievable vs requested), then let the user loosen ONE.

**Expose feasibility** so the orchestrator can diagnose: on a miss, return the `best` achieved + which constraint was binding (§21); read gen-layout's `layout_difficulty`/score-ceiling from metadata.

---

## 23. Special cells (OPTIONAL — only when the design asks)

Reference Mission/Bonus levels carry SPECIAL cells beyond normal match-3 tiles. Each has its OWN
correct step and stage — NEVER mix them into base gen (keeps the v3 solver on a clean board):

| Special | What (reverse-engineered) | Stage | Tool |
|---|---|---|---|
| **STACK** | straight vertical pile (same x,y all layers, no +0.5 stagger); registered in `stacks:[{x,y,d}]` | GEOMETRY — **before tiles** | `gen-layout/scripts/add_stacks.py` (pattern + symmetric) |
| **BONUS `1001`** (round) / **MISSION `1002`** (square) | a NON-match-3 **cover** that AUTO-CLEARS when its footprint is clear on top. **Direction C:** specials are ADDED as interstitial covers over a COMPLETE ÷3 normal board — they NEVER consume a match-3 cell (normals alone stay ÷3). Footprint = **2×2 or 3×3**, encoded by `s`: MISSION `0.7`=2×2 / `1.0`=3×3; BONUS `0.9`=2×2 / `1.4`=3×3 (collision half 1.0 / 1.5 — shared with player + solver). Placed offset/straddling, within layout bounds, covered-at-start; overlapping specials STACK on distinct layers. | added **after a solvable normal board** (built in one pass) | `scripts/reserve_special.py --bonus N --mission M` (no `--*-cover` → **auto-mix** 2×2+3×3; force with `--mission-cover/--bonus-cover 2x2\|3x3`; explicit counts `--mission-2x2/--mission-3x3` etc.; `--size` overrides `s`) |
| **MYSTERY `o:[0]`** (legacy `m:true`) | a NORMAL match-3 tile that is FACE-DOWN — colour FIXED at design time. It stays COVERED on the board **even when pickable**: the player picks it BLIND and its real colour is revealed only once it lands in the TRAY (distinct from CLOUD, which reveals on-board when uncovered). Plays as a normal tile (÷3 unchanged) → no effect on geometry/balance/solvability. Placement: **RANDOM, any layer**, 3-5 per level. `o`: **0=mystery, 1=cloud** (`m:true` is the OLD marker, still read) | **after tiles** | `scripts/add_special_cells.py --mystery N` (omit N → random 3-5; emits `o:[0]`; `--mark` is a kept alias) |
| **CLOUD `o:[1]`** | a NORMAL match-3 tile covered by the mystery cover art (fills the WHOLE tile); the cover clears MISSION-STYLE (the instant nothing on a higher layer overlaps it = when it becomes pickable), revealing the real face — only the cover layer clears, the tile stays. Plays as a normal tile → NO effect on solvability (solver ignores `o`). Placed as a SYMMETRIC region on the BOTTOM layer(s) 0-1 only (NEVER the top — must start covered), ~33% of tiles. Candidate cells must be COVERED **and VISIBLE (peek)** — no tile directly on top — so cloud levels REQUIRE a **STAGGERED layout** (gen-layout default `uniform_stagger`, §9); a COLUMNAR layout hides every bottom cell → add_cloud places 0. `o` value: **1=cloud, 0=mystery** | **after tiles** | `scripts/add_cloud.py` (default ~33%, `--cloud-pct`/`--cloud N`, `--axis auto`, `--layers 0,1`) |

Key rule (direction C): `reserve_special` first assigns a full **v3-solvable NORMAL level** (÷3), then
ADDS each special on an interstitial layer over a 2×2/3×3 cluster — no normal cell is removed, so the
match-3 set stays ÷3. It hard-verifies with `scripts/solve_special.py` (`solve_v3_special`, footprint-
aware) that the board is solvable AND every special is covered-at-start (won't auto-clear immediately).
To solve a level FILE yourself: `python solve_special.py <level.json>` (its CLI builds the 2×2/3×3
footprint map from `s` so 3×3 specials aren't under-modelled) — or programmatically pass
`special_halves=special_halves_from_level(data)`.

**Mystery (`o:[0]`) needs NO re-verify**: it is a normal match-3 tile that is merely face-down (fixed
colour, revealed only when picked into the tray), so it cannot change a level's solvability. Add it
LAST, after the level is already solvable, with `add_special_cells.py --mystery N` (default random 3-5,
emits `o:[0]`; legacy `m:true` still read).

**Final step — match the game format exactly:** the generators emit a `metadata` block; the game
LEVEL format is `{group,tiles,layers,stacks,bg,bgm,sl,dif}` (no metadata; `dif=1` constant). **`sl` is
DERIVED from content**, not constant: a MISSION level (any `i=1002`) → `sl=2`; else a BONUS level
(`i=1001`) → `sl=1`; a normal / mystery-only level → the `sl` key is OMITTED (verified: BonusLevel=1,
MissionTile=2, mystery-only have none). Run `scripts/export_game_format.py <level.json>` last.

```bash
# image → level with bonus + mission + mystery, game-ready:
python ${CLAUDE_SKILL_DIR}/../gen-layout/scripts/add_stacks.py NewLayout_x.json --n 4 --out x_stk.json   # optional
python ${CLAUDE_SKILL_DIR}/scripts/reserve_special.py x_stk.json --bonus 4 --mission 3 --color-count 12 --out lvl.json
python ${CLAUDE_SKILL_DIR}/scripts/add_special_cells.py lvl.json --mystery 4 --out lvl_m.json   # optional, post-tile
python ${CLAUDE_SKILL_DIR}/scripts/export_game_format.py lvl_m.json --out lvl_game.json
```
