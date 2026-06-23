# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hard requirements (user-enforced, MUST follow)

These are explicit invariants the user has asked to be preserved across sessions. Any new script, metric, or analysis in this project MUST satisfy all of them.

1. **Solver MUST be DFS-based.** Use `verify_smart_v3.solve_v3` (DFS + transposition table + atomic triples) or `solve_path.solve_with_path` (DFS with recorded pick sequence) for every solvability check and every winning-path extraction. Do NOT fall back to beam BFS, Monte Carlo, or the stock `TileSolver.analyze` — those are retained only for sanity comparison and give wrong answers on many real levels.

2. **Game-over rule is tray = 7 slots full without a triple.** After every pick, run the auto-clear, then check `len(tray) >= 7 AND no tile type has count ≥ 3` — if true, it's game over. Any solver/replay/playout code must use this exact check (NOT `> 7` and NOT just `>= 7` without the triple guard). Breaking this produces solutions that instantly lose in the real game.

3. **"Layer dễ" (easy layer) definition**: a layer is considered easy if, during a match sequence that clears it, the tray never reaches `>= 6` tiles at any step. That is, `max_tray_size_during_clear <= 5`. This is stricter than the game-over ceiling (7) — easy means the player has comfortable headroom. Metrics for "top N layers easy" must verify this ≤5 ceiling on the actual pick sequence (v3 replay), not just on static tile distribution.

4. **Layout difficulty sweep MUST iterate the user-specified tile_count range and report min/max per tile_count.** The canonical script is `difficulty_minmax.py`. For each `(layout, tile_count)` pair, run N samples (default 20) with varied knob presets, track `final_score` min/max. Output CSV with columns `layout, tile_count, score_min, score_max`.

5. **If requested tile_count exceeds layout capacity, SKIP and REPORT, do not silently fall through.** Layout capacity = `total_cells // 3` (each tile type needs at least 3 copies to form any triple). When generating or sweeping with `tile_count > capacity`:
   - The gen engine will effectively cap at `capacity`, producing fewer distinct types than requested — do not record this as if it was the requested count.
   - Either: (a) skip the combo entirely and log `"layout X capped at Y types, skipping tile_count Z"`, or (b) record only the actual effective tile count and label the row accordingly. Never emit a row claiming `tile_count=25` on a 30-cell layout.

6. **Parallel search MUST use 8 workers.** Launch with the fixed seed set `1 11 23 47 101 239 991 1001` (chosen to spread RNG without collisions) via shell fork:
   ```bash
   for seed in 1 11 23 47 101 239 991 1001; do
     python find_*.py $seed > log_$seed.log 2>&1 &
   done
   ```
   First successful worker saves its candidate to `*_candidate.json`; kill the rest via `wmic process where "CommandLine like '%%find_*%%'" delete`. Do not run single-worker search for anything that needs score filtering — it's too slow on cache-miss random seeds.

### Additional invariants (from bug experience)

- **Display labels are `tile_id + 1`.** Internal `tile_id` is 0-indexed (0–24). Game UI renders 1-indexed labels (1–25). Always convert when printing picks to the user and when parsing what the user sees on screen.
- **Atomic triple intermediate bounds**: the v3 optimization "pick 3 same-type tiles in one step" must check that intermediate tray size during the 3 picks stays `< 7`: `cur_tsize + (needed - 1) < TRAY_SIZE`. Skipping this check lets the solver emit solutions whose real playback hits game-over mid-atomic.
- **Clear `tile_id` to `-1` before regeneration**: sample layouts loaded from `sample_levels/` retain stale tile IDs from whatever run last wrote them. If passing to `generate_tiles` / `auto_generate`, reset every cell first, otherwise some gen code paths treat the board as already-assigned.
- **Use `load_board_from_path` with an absolute path**, not `load_board(file)` — the latter depends on an internal default levels dir that's often unset.

## What this project is

**Tile Level Simulator v3.60** — a tool for designing Triple Match puzzle game levels (Tile Explorer / TE game). Reverse-engineered from Unity game binary. Levels are JSON layouts (empty cells only); tiles are assigned by the generation engine at runtime.

## Running things

```bash
# MCP server (Claude Code picks this up automatically via .mcp.json)
python tile_mcp_server.py

# GUI app (runs tkinter on main thread — must run directly, not via daemon thread)
python tile_level_simulator.py

# Or use the pre-built executables (no Python needed)
TileLevelSim.exe
TileMCPServer.exe
```

**Windows GUI caveat**: Launching a tkinter window from a subprocess requires routing through the Windows shell to get desktop access. Use `subprocess.Popen(['cmd', '/c', 'start', '', sys.executable, script_path])` — not `threading.Thread` (daemon threads can't create windows on Windows).

## Architecture

```
tile_level_simulator.py  ← ~4900 lines — core engine + full tkinter GUI (PlayWindow)
tile_api.py              ← ~850 lines  — headless JSON-serializable API layer
tile_mcp_server.py       ← ~500 lines  — 36 MCP tools (FastMCP, stdio mode)
tile_metadata.py         ← ~500 lines  — metadata, pinned lists, project collections
tile_logger.py           ← ~100 lines  — JSON-line event logger → tile_events.log

# Custom fast solvers (built in this project, not part of original simulator)
verify_smart_v3.py       ← DFS + transposition table + atomic triples (~10000x faster than stock MC)
verify_smart_fast.py     ← bitmask beam BFS (legacy, kept for sanity check)
solve_path.py            ← v3 variant that records the winning pick sequence
count_solutions.py       ← memoized DP for exact winning-path count

# Level-design search scripts (use as templates for new constraints)
find_easy_first_half.py  ← window-metric search: "top N layers easy" constraint
find_easy_top3.py        ← top-3 distribution search (legacy metric)
find_80fail.py           ← high random-fail-rate search
find_unsolvable.py       ← deadlock search (exhaustive beam proof)
difficulty_minmax.py     ← sweep all layouts × tile_count → CSV
```

### Data model (tile_level_simulator.py)

- **`Cell`** — single tile slot: `x`, `y`, `tile_id` (-1 = unassigned), `layer_idx`
- **`Layer`** — ordered list of `Cell`s; lower index = bottom (more covered)
- **`Board`** — ordered list of `Layer`s; `board.all_cells()` returns all cells bottom-to-top

### Generation engine: `TEEngine`

Reverse-engineered port of Unity's tile assignment pipeline. Key params:

| Param | Effect |
|---|---|
| `color_count` | 2–25 tile types (game supports 2–9; 10–25 are tool-only extended) |
| `hard_code` | 0–3; adds extra color types (+1 at ≥2, +1 again at 3) |
| `up_easy` | Top 1 layer gets only easy (low-count) tile types |
| `top2_easy` | Top 2 layers easy |
| `top3_easy` / `top4_easy` | Extended knobs for top 3/4 layers |
| `less_type` | Reduces type variety in middle layers |
| `distance` | 0–15; spreads same-type tiles farther apart → harder |
| `val_replace` | TileValueReplace post-process (level 51+) |
| `val_mode` | 0–3; controls value replacement strength |
| `binding` | `"random"` (default) or `"preset"` |

Generation pipeline order: `_build_icon_pool` → `_assign_hard_bg` → `_bind_random/_bind_preset` → `_fix_x3_distribution` → `_apply_value_replace` → `_check_solution` (up to 10 retries).

### Scoring: `DifficultyScorer`

`final_score = layout×X + inter_group×Y + intra_group×Z + cover100×K`

Weights tuned to **X=0.3, Y=0.3, Z=0.5, K=0.6** (in `scoring_weights.json`).

**effective_layer concept** (NEW): `eff_layer = #higher_physical_layers_with_overlap + 1`. Top tiles = 1, deeply buried = N+1.

| Component | Computed on | Notes |
|---|---|---|
| **layout** | Full board, physical `layer_idx` | BFS resolve count, unchanged |
| **strip 2-window** | Active set, **effective_layer** | Triples within `max_eff - min_eff ≤ 2` |
| **same-type subtract** | Physical layer (above me) | -1 (NOT -N) intentional: hidden tiles aren't "easy" from player view |
| **cover100** | Active after strip, **effective_layer** | Cells at `max(eff_layers)` and max > 1 |
| **inter_group / intra_group** | Active after strip, effective scores | Stripped tiles count as effective=0 |

**Re-sweep needed if scoring changes** — `difficulty_minmax_combined.csv` was re-swept (21 min, 2636 rows). Score range expanded for deep layouts (max ~120 → ~200).

`score_level` returns a single-pass score; `batch_score` / `auto_generate` with `final_min_max` target gives Min/Max across N runs (reflects true difficulty range since tile assignment is random).

### Level JSON format (stones format)

Layout files in `sample_levels/` use the game's native "stones" format:

```json
{
  "group": 1,
  "tiles": "",
  "layers": [
    {"index": 0, "stones": [{"i": 2, "x": -2.0, "y": 3.5}, ...]}
  ],
  "stacks": []
}
```

`i` = tile_id (0 = no tile assigned yet). The API layer auto-detects this format in `_parse_layers_from_data`. All `api_*` functions work with an internal board dict format (layers with cells containing x/y/tile_id).

## MCP workflow

`.mcp.json` configures the server. Claude Code loads it automatically.

Standard level creation workflow via MCP tools:
1. `load_board_from_path(filepath)` — load a layout using an **absolute path** (e.g. `c:/Users/.../sample_levels/NewLayout_L74.json`). `load_board(file)` + `list_level_files()` rely on an internal default levels directory that is often empty/unset; prefer the path-based variant when working from `sample_levels/`.
2. `generate_tiles(board_dict, params)` — assign tiles, get `{board, stats, score}`
3. `auto_generate(board_dict, params, target)` — server-side loop to hit a score range (use `score_min`/`score_max` for single-pass, `final_min_max` for Min/Max target)
4. `full_report(board_dict)` — combined difficulty + solvability
5. `play_level(board_dict)` — opens interactive play window on user's desktop
6. `export_stones(board_dict, filepath)` — save to JSON in stones format

**Regeneration gotcha**: sample layouts loaded from `sample_levels/` may come back with stale `tile_id` values from a prior run. If you want `auto_generate` / `generate_tiles` to actually regenerate, reset every cell's `tile_id` to `-1` before passing the board dict in — otherwise the engine treats the board as already-assigned in some code paths.

Bulk tools: `bulk_score_levels`, `difficulty_curve`, `generate_level_batch`, `generate_difficulty_progression`, `export_unity_report`.

## Sample levels

`sample_levels/` contains 116 layouts (named `NewLayout_L1.json` … `NewLayout_L116.json` plus `NewLayout_70.json`, `NewLayout_113.json`). These are **empty layouts** (no tiles); tiles must be generated before scoring or playing.

## Difficulty presets

`DIFFICULTY_PRESETS` in `tile_level_simulator.py` maps preset names to full param sets:
- Tutorial (1-50): cc=3, no knobs
- Mid-game (51-100): cc=4, up_easy, val_replace
- Hard (101-500): cc=5, hard_code=1, distance=3
- Very Hard (500+): cc=6, hard_code=2, distance=5
- Extreme: cc=7, hard_code=3, distance=8

## Logging

All API calls log to `tile_events.log` (JSON-line format, 10 MB rotate, 2 rotated files kept). Use `get_recent_logs(n)` MCP tool or read the file directly to debug generation issues.

## Game rules (critical — easy to get wrong)

- **Game over condition**: `len(tray) >= 7 AND no tile type has count ≥ 3` — check is AFTER insert AND auto-clear. The old code (and the stock `TileSolver`) used `> 7` which silently accepts invalid tray=7 states. Any new solver MUST use `>= 7` with the triple-check, otherwise "solutions" it emits will instantly lose in the real game.
- **Display labels are 1-indexed**: game UI shows tile labels `1`–`25`, but internal `tile_id` is 0-indexed `0`–`24`. When showing a pick sequence to the user, always display `tile_id + 1`. When the user reads a tile off the screen, subtract 1 to map to internal id.
- **Atomic triple optimization** (in v3 solver): when ≥3 pickable tiles share a tile type, pick all of them in one step. MUST also bound-check intermediate tray size during the 3 picks: `cur_tsize + (needed - 1) < TRAY_SIZE`. Forgetting this lets the solver emit a "solution" whose real playback hits game over mid-atomic.
- **Atomic triples are always safe**: picking 3 same-type pickable tiles always reduces the board and never harms tray state (intermediate bounds aside), so the v3 solver takes them eagerly without branching.

### Buffs / boosters

`PlayWindow` exposes 3 buffs: `Shuffle` (3 uses), `Undo` (3 uses, returns last 3 picks to board), `+1 Slot` (1 use, expands tray 7→8).

**Shuffle** — dynamic triple count + absolute tray priority:
1. Tray has ≥3 distinct types → force up to **3 triples**; otherwise up to **2**.
2. **Absolute tray priority**: Phase 1 = types already on tray (2 on tray > 1); Phase 2 = types NOT on tray.
3. Smart force: only `3 - on_tray` copies forced per type. Relaxed candidate filter: `board_copies >= 3 - on_tray`.
4. Fallback to plain random if no valid type found.

**Undo** — returns **1 tile** (most recent pick) from tray. 3 uses per level (changed from 3 tiles to 1).

**+1 Slot** — expands tray 7→8, one-time use.

**Restart bug fix**: `_original_tile_ids` saved at init, restored on restart (Shuffle modifies tile_ids in-place).

**Implication for solvers**: buff usage is NOT modeled in `verify_smart_v3` / `solve_path`. Those solve the level with tray=7 hard ceiling and no buffs. A level reported as "unsolvable" by v3 may still be beatable by a real player using Shuffle/Undo/+1Slot. Don't conflate "v3 unsolvable" with "unwinnable" — they're different bars.

## Custom solver usage

**When to reach for which solver**:
- Solvability check / winning-path extraction → `verify_smart_v3.solve_v3(board, max_expansions=N)`. Returns `(True|False|None, depth, expansions)`. `None` = cap hit (treat as likely-solvable when screening candidates).
- Full pick sequence for a solvable level → `solve_path.solve_with_path(board, max_expansions=N)` returns `(result, picks_list, elapsed, cells)`. Use `tile_ids[i] + 1` when printing picks to the user.
- Exact count of distinct winning paths → `count_solutions.py`. Finishes in ~15s for 69-cell boards, results commonly reach 10³⁰⁺.
- "Is this level solvable by the stock MC?" → ignore it. The stock `TileSolver.analyze` has a hardcoded 500-run cap and a greedy random heuristic; it will declare many solvable levels unsolvable and vice versa. Always use v3.

**Parallel workers for search**: the level-design scripts take a `sys.argv[1]` seed. Launch 8 in parallel via shell fork:
```bash
for seed in 1 11 23 47 101 239 991 1001; do
  python find_easy_first_half.py $seed > log_$seed.log 2>&1 &
done
```
Seeds chosen to spread RNG. Kill with `wmic process where "CommandLine like '%%find_x%%'" delete`. Python stdout buffers when redirected, so early logs may be empty until a filter hit flushes.

## Custom tile assignment (bypass TEEngine)

When TEEngine can't produce extreme distributions (e.g., "top 3 layers pure easy with 17 types"), bypass it entirely with manual tile assignment:

- **3 assignment strategies**: Priority (pickable cells), Cascade (vertical stacks), Random. Check `layout_strategy_analysis.csv` for which to use per layout.
- **Bridge Distribution**: 3-4 type groups (easy-only / bridge / hard-mid / trap-only). Bridge types span top AND bottom so player recognizes them when revealed. Learned from analyzing real Yellow L21 level.
- **Critical rules**: never place easy triples on cover100 cells (invisible); bridge must form matchable triples at bottom; top layers must have ≥2 instant triples.
- **Math**: `n_easy × 3 + n_bridge × 6 + n_trap × 3 = total_cells`

### 9 template scripts for level design

| Script | Pattern | Any layout |
|---|---|---|
| `find_trap_fast.py` | Trap ẩn / 90% fail | **Yes** |
| `find_easy_first_half.py` | Top layers easy (window metric) | Yes |
| `find_hybrid_fast.py` | Hybrid random assignment | Yes |
| `find_hybrid_priority_v2.py` | Hybrid priority (cover100-aware) | L20-style |
| `find_hybrid_cascade_L21.py` | Cascade vertical stacks | L21-style |
| `find_bridge_L21.py` | Bridge distribution (easy/harder/hard) | L21 |
| `find_bridge_hard_L21.py` | Bridge hard (2 types, 1/layer) | L21 |
| `find_guided_trap_L21.py` | Guided Trap (breadcrumbs + cascade) | L21 |
| `find_clear50_trap.py` | Clear 50% then trap (auto-strategy) | **Yes** |
| `gen_all_9.py` | **All 9 patterns in parallel (~20s)** | Mixed |

**Fastest way to generate all patterns**: `python gen_all_9.py` → outputs `all_9_boards.json` with 9 verified levels in ~20 seconds.

### Speed optimization rules

1. Filter order cheap→expensive: type_count → score → v3(100k) → greedy(30) → greedy(300)
2. Precompute bb[] once (layout-only)
3. Clone in-memory (not `load_board_from_file` per iteration)
4. 2-stage greedy: 30-50 quick → 300 only if pass
5. Unique output files per worker: `*_s{seed}.json`
6. Double-verify before play: v3 → solve_path → save unique JSON → play saved

### Reference CSV files

- `difficulty_minmax.csv` — TEEngine-based min/max per (layout, tile_count)
- `difficulty_minmax_custom.csv` — Custom assignment min/max (wider range)
- `difficulty_minmax_combined.csv` — Both methods merged (true min/max)
- `layout_strategy_analysis.csv` — 117 layouts classified: Cascade/Priority/Random

## Level-design metric playbook

Five metric styles have been tested empirically against the engine. Reach for them in this order:

1. **2-adjacent-layer window triple metric** — for any "top N layers easy to play" ask. For each 2-layer window within top N, a tile type is "easy" if it has ≥3 copies in the window; measure fraction of top-N tiles belonging to easy types. Threshold around 0.85. Matches how players find triples by eye. Use `find_easy_first_half.py` as the template.
2. **Top-half distribution metric** — count types with ≥3 copies in the top half of cells (`partition_top_half`). Use for "first 50-60% easy" style asks.
3. **Deadlock depth via exhaustive beam** — for "unsolvable / clear X% before deadlock" asks. Run v3 to exhaustion; accept only when `visited < beam_width` (proving exhaustive exploration) AND `best_depth_reached >= required_fraction * total_cells`.
4. **Random playout fail rate** — for "N% of naive paths deadlock" asks. 500 greedy playouts (10% noise); require `fail_rate >= 0.80` AND v3 confirms at least one solution exists. Only trust this for extreme fail rates (80%+).
5. **Tray pressure profile along v3 path** — avoid for "easy→hard" asks. v3's atomic-triple path keeps tray flat at ~6, so profiles don't reflect perceived difficulty.

**Layout pool selection** is math-constrained:
- Deep layouts (5-7 layers like L50, L115) have small top-3 (~18 cells), capping top-3 to max 6 triple-ready types.
- 4-layer layouts (L86, L70, L18) have top-3 ≈ 50-60 cells with room for 10-15 types.
- 3-layer layouts give top-3 = 100% of cells but sacrifice depth-based score.

**Relaxation pattern when no candidate matches**:
1. Widen score range first (e.g. 60-80 → 50-70).
2. Then top-3 thresholds (max_types 5 → 8, triple_frac 0.90 → 0.85).
3. Never silently relax the user's explicit tile-count range.

**"Best-effort" fallback**: if the strict filter never hits, the script's `best` tracker holds the closest candidate found — often good enough to present with a note about which thresholds it missed.
