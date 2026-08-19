---
name: Greedy-pick detection vs exact solving — 4 mechanisms, don't conflate them
description: Decision table for the 4 distinct mechanisms that touch "does the obvious/greedy move differ from the exact answer" — what each is for, and what it must NOT be used for
type: reference
---

Four separate mechanisms in this codebase all relate to "greedy vs exact" in some way. They get
confused easily because they sound similar. This doc exists so nobody reaches for the wrong one.

| Mechanism | Location | What it is | Valid use | Do NOT use for |
|---|---|---|---|---|
| **`playout()`** (stochastic evaluator) | `scripts/gen_pattern.py`, function `playout()` | Simulates a naive/greedy PLAYER over many games (`mode="greedy"`: prefer completing a triple > pair > random, 10% pure-random noise; `mode="random"`: uniform-random). Returns `(fail_rate, avg_cleared)`. | "Trap ẩn" (hidden trap) classification ONLY — the pattern is literally defined as `dfs_solvable AND fail_rate >= 0.90` (`hidden_trap_levels.md`). | **General difficulty ranking.** Proven empirically too harsh (`difficulty_design_workflow.md`: "Random/greedy playout survival rate → too harsh, v3 atomic-triple path is nothing like a random player" — listed under "metrics that failed"). Use `new_diffScore` for ranking. |
| **`min_safe_choices`** (exact per-step probe) | `scripts/min_safe_choices.py` | Walks the first `check_depth` steps of ONE proven winning DFS path; at each step, counts how many currently-pickable moves are still exactly-verified "safe" (still winnable). `min_safe==1` while `total_pickable>1` = a bottleneck. NOT stochastic — every count is exact. | Opening-forgiveness / bottleneck detection, complementing `new_diffScore` (`SKILL.md §3.2`). | Full-level trap classification — it only ever examines `check_depth` steps of ONE path, not the whole level. Not wired into any scoring pipeline; standalone CLI/import only. |
| **Atomic-triple collapse** (solver-internal heuristic) | `engine/verify_smart_v3.py`, inside `solve_v3`'s `dfs()` ("Optimization 1: atomic triple") | Inside the EXACT DFS solver: when ≥3 same-type tiles are pickable and taking them is provably always safe, take them immediately instead of branching. A sound acceleration of exhaustive search — not stochastic, not a "greedy player." | Nothing external — it's plumbing inside `solve_v3` itself. | **Never use as a standalone metric.** Don't conflate with `playout()` — this is not "how would a naive player do," it's "this move is provably never wrong, so don't waste branches on the alternative." |
| **`TileSolver.analyze`** (stock, deprecated) | `engine/tile_level_simulator.py`, class `TileSolver`, method `analyze` | The ORIGINAL engine's difficulty verdict — a hardcoded 500-cap random Monte Carlo simulation. | Nothing. Deprecated. | **Anything.** `SKILL.md §2` already forbids it ("NEVER use stock `TileSolver.analyze` — hardcoded 500-cap MC, unreliable"). If you see a `"Verdict"` block referencing `solve_rate`, that's this — not `playout()`, not `min_safe_choices`. |

## The one place these two get combined on purpose

`analyze_level.py --solve-profile` (`SKILL.md §3.4`) is the only place `playout()`'s greedy-fail-rate and
the exact DFS verdict (via `solve_dispatch.solve_any`) are combined into one persisted, labeled
conclusion: `metadata.solve_profile = {"dfs_solvable", "greedy_fail_rate", "classification"}`. It reuses
the SAME 0.90/<0.20 thresholds already established by the "trap ẩn" pattern — nothing new invented.
**It is explicitly NOT a difficulty ranking metric** — same scoping discipline as `min_safe_choices`:
it answers "does the obvious path diverge from the necessary path," which is orthogonal to
`new_diffScore`. Never sort/compare levels by `solve_profile.classification` in place of `new_diffScore`.

v1 scope is DFS + `playout()` only. Folding `min_safe_choices`'s exact per-step signal into the same
field (e.g. a `bottleneck_at_step` sub-field) is a possible v2 follow-up, not done here.

For a different but related question — "can the DFS itself be made faster by pruning the search
tree" — see `reference/solver_pruning_history.md`. Atomic-triple collapse (row 3 above) is sound
*inside* `solve_v3`'s own DFS; that history file covers why the SAME idea is unsound when reused for
an existence query like `winnable`/`min_safe_choices`, plus what else was tried and rejected.
