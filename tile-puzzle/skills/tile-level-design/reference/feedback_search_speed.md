---
name: Search speed optimizations
description: Performance lessons for level-search scripts — filter order, precompute bitmask, avoid disk reload, validate=False
type: feedback
originSessionId: 9cb29a82-5617-4dd8-9f97-2bb165e50048
---
Level-search scripts should be optimized for speed. Key lessons from bugs and benchmarks:

1. **Filter order: cheapest first.** tile_count (~0ms) → score (~1ms) → v3 solvable (~10-500ms) → greedy playout (~200-2000ms) → solve_path (~100-3000ms). Never run v3 before checking tile count and score.

2. **Precompute blocking bitmask once.** `build_bb()` depends only on cell positions (layout), not tile_ids. Compute once outside the loop, reuse every iteration. `find_hybrid_custom.py` does this correctly; `find_l20_17.py` recomputes every iteration via board reload.

3. **Cache template board, don't reload from disk.** `load_board_from_file(path)` reads disk every call. Load once, then clone positions + assign new tile_ids each iteration.

4. **`eng.validate = False`** skips TEEngine's internal 10-retry + stock solver check. Use v3 for solvability instead — faster and more accurate.

5. **8 parallel workers** with unique output files per worker (e.g. `candidate_seed_N.json`) to avoid overwrite bugs.

6. **Relaxation pattern** when no match: widen score → relax thresholds → change layout. Don't waste cycles on impossible constraints.

7. **2-stage greedy**: Run 30-50 greedy playouts first (quick reject). Only run full 300 if fail_rate > 0.5 in quick stage. Saves ~80% of greedy time on non-trap candidates.

8. **Clone in-memory instead of Board constructor**: Use `clone_board(positions, tile_ids)` that builds Board from cached position array, not `load_board_from_file()`. Measured: 1130s → 0.5s (2260x speedup) on `find_hybrid_custom.py`.

**Benchmark results (9 templates parallel on L20+L21)**:
- Before fixes: ~30 minutes sequential
- After fixes: **69 seconds parallel** (all 9 levels)

**IMPORTANT: Benchmark MUST include full request → play window opens** (not just gen time):
- Gen time: time spent in find_*.py scripts
- Open time: time to call api_play_level for each level
- Real benchmark example: 5 L31 levels = 4.8s total (4.7s gen sequential + 0.1s open). Parallel could cut to ~1-2s if scripts use unique output files (`*_s{seed}.json`) to avoid race conditions on shared candidate file.
- Bottleneck scripts fixed: `find_hybrid_custom.py` (1130s→0.5s), `gen_5_patterns.py` P1/P4 (2-stage greedy 5x faster)

**Why:** A single search iteration takes ~1-5ms for generation+scoring, but ~100-2000ms for v3+greedy. Filtering 99% of candidates before reaching v3 cuts total search time 10-100x.

**How to apply:** In every new `find_*.py` script, structure the loop as: generate → tile_count filter → instant_triples filter → score filter → v3(100k cap) → greedy(30 quick) → greedy(300 full) → solve_path. Precompute `bb` once before the loop. Clone board in-memory.
