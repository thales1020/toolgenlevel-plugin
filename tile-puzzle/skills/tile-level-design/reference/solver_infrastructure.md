---
name: Solver infrastructure in GD_Test
description: Custom solver + level-design scripts built in this project, what each does, which to reach for first
type: reference
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**`verify_smart_v3.py`** — the fast solver. DFS + transposition table + atomic triples. ~10000x faster than the stock Monte Carlo in `tile_level_simulator.TileSolver`. Use this for solvability check and dead-level detection. `solve_v3(board, max_expansions=N, verbose=False)` returns `(True|False|None, depth, expansions)`.

**`verify_smart_fast.py`** — beam BFS version with bitmask state. Obsolete now that v3 exists; keep around for sanity checks.

**`solve_path.py`** — like v3 but records the winning pick sequence. Use when the user wants the actual solution, not just "solvable yes/no". Accepts `max_expansions` cap.

**`count_solutions.py`** — memoized DP that counts ALL winning paths. Uses same state encoding as v3. Fast enough for 69-cell boards (~5-15s). Outputs astronomical numbers (10^30+ is normal).

**`find_easy_top3.py`** — level-design with top-3 distribution metric (count types + triple-ready types in top 3 as a whole). Use when top 3 has plenty of cells (4-layer layouts).

**`find_easy_first_half.py`** — level-design with **2-adjacent-layer window** metric. Slides a 2-layer window through top 3, counts tiles belonging to types with ≥3 copies in any window. This matches player intuition best — "can I see a triple by looking at 2 adjacent layers?". **Preferred metric for "layer dễ"-style asks.**

**`find_80fail.py`** — find solvable levels with N% random failure rate. Less useful than distribution-based because random playouts don't reflect real play.

**`find_2phase.py` / `find_2phase_v2.py`** — find 2-phase difficulty via tray profile. Mostly unsuccessful; v3 packs tray flat. Don't reach for this unless no alternative.

**`find_unsolvable.py`** — find levels where beam search proves no winning path. Works but slow; mostly superseded by v3's dead-state detection.

**How to apply:** Start any new level-design task with `find_easy_top3.py` as the template (it has the cleanest generate→filter→verify loop). Copy and modify the metric to match the new constraint. Use v3 from `verify_smart_v3` for solvability; use `solve_path` if the user will want to see the solution.
