# Changelog — tile-puzzle

## 0.9.6 — FIX: regenerating a level that already has a mission/bonus tile silently destroyed it

**Bug, confirmed and fixed.** Regenerating (re-tiling) a level that already carried a mission tile
would silently turn that mission cell into an ordinary color tile — losing the mission tile entirely,
corrupting the level's tile count, and making the solvability check run against the wrong board.

Root cause: `gen_pattern.py::_load_trimmed` and `reserve_special.py::_gen_normal_level` both load the
input file and then discard/overwrite `tile_id` on EVERY cell before assigning fresh colors
(`_load_trimmed` keeps only `(x,y,layer_idx)`, throwing away `tile_id`; `_gen_normal_level` calls
`board.clear_tiles()`). Neither checked whether the loaded cells already included a special
(`tile_id >= 1000`, bonus 1001 / mission 1002). Both tools are documented to expect a bare,
geometry-only layout (no tiles) — but nothing enforced that, so pointing either at an already-built
special level silently wiped the special. Downstream effects: the ÷3 normal-cell count included the
special's position (wrong denominator), and `solve_v3` (not `solve_v3_special`) ran on the
now-corrupted board, so the reported solvability no longer matched the level the user thought they had.

Fixed: both loaders now hard-fail (`SystemExit`) the instant they see any `tile_id >= 1000` in the
loaded input, before touching any tile_id — pointing them at an already-special level is refused
outright instead of silently corrupted. See `reference/game_rules_and_bugs.md` for the full writeup.
Specials remain a separate POST-step (`reserve_special.py` / `add_special_cells.py`) on a finished
BASE (no-special) level — never mixed into a re-tiling/regen pass.

## 0.9.5 — REVERT: 0.9.0's ÷3 guard in `solve_v3` was wrong, incorrectly rejected winnable boards

**Regression, confirmed and fixed.** The 0.9.0 changelog entry below (kept as-is, historical record —
see the correction here instead of editing it) describes a `solve_v3` guard added on the reasoning
"a NORMAL board with `total_cells % 3 != 0` can never fully clear — always a caller bug." That
reasoning was **wrong**, caught by the user pointing at another machine's plugin output for a real
level (level 873: 77 cells, one tile type at 8 copies — not a multiple of 3 — genuinely solvable).

Confirmed directly against the game engine's actual win check
(`tile_level_simulator.py PlayWindow._pick_tile`): `if not self.active: self.won = True`, checked
BEFORE the game-over/lose condition. **Win is the board being empty (every cell picked), NOT the tray
being empty.** A tile type whose count isn't a multiple of 3 just leaves 1-2 tiles stuck in the tray
permanently once picked — that is still a win, as long as the tray never reaches 7 with no available
triple at any point along the way. `solve_v3`'s own DFS already encoded this correctly
(`if active == 0: return True`) — the 0.9.0 guard was short-circuiting BEFORE that correct search
could run, rejecting real winnable boards with a `ValueError` instead of solving them.

- **Reverted**: the `n % 3 != 0` early-`ValueError` guard removed from `solve_v3` in both engine
  copies (`tile-level-design/engine/` and `gen-layout/engine/`, byte-parity restored). Verified: a
  hand-built 8-cell single-type board (matching the reported case) now returns `True` instead of
  raising.
- **NOT reverted** (different, still-valid concern): `gen_pattern.py`/`reserve_special.py`'s
  hard-fail-by-default when trimming a layout to ÷3 for tile assignment. That guard is about not
  *silently* dropping cells from a named layout's geometry (Task 1, 0.9.0) — a data-integrity concern,
  unrelated to whether ÷3 is required for solvability. Their per-type ÷3 default is a generator DESIGN
  CONVENTION (clean, no-leftover distributions), not a solvability requirement.
- Corrected the same false claim everywhere it had propagated: `SKILL.md` §2,
  `reference/game_rules_and_bugs.md` (new entry), and the root `TileLevel_AI_KnowledgeBase.md` §0.4 /
  §3.3 / §3.4 (the authoritative spec doc — this is where the original, incorrect "÷3 rule" was first
  written; a hard "if wrong, impossible regardless of arrangement" claim that had never actually been
  checked against the engine's real win condition, despite the doc's own claim that "every number here
  is verified against real game data or the solver").
- **Lesson**: a hard-fail guard framed as protecting against wasted solver time is itself a claim
  about game rules that needs the SAME evidence bar as everything else in this project — verify
  against the actual engine, not against an assumption that sounds structurally obvious ("3 tiles per
  match, so counts must be multiples of 3"). It sounded right and wasn't checked against
  `PlayWindow._pick_tile` until a real rejected level forced the question.

## 0.9.4 — new script: `diffscore_range.py` (achievable new_diffScore range for a layout)

New function, requested directly: given a layout, return the min/max achievable `new_diffScore`.

- `scripts/diffscore_range.py <layout> [--n-types N] [--samples 3] [--v3-cap 15000] [--time-budget 15]`
  — a probe over a handful of SOLVABLE boards only.
  - `--n-types N` given: sweeps only that value, reports min/max across `--samples` solvable attempts.
  - Omitted: sweeps the design rule's default range **10–20** (§4.4/0.9.2), clamped to the layout's
    capacity — e.g. capacity 13 sweeps `{10, 13}`, not `{10, 15, 20}`. Reports the global min/max
    across all points, plus which `n_types` achieved each.
  - Fails loudly and immediately (no wasted attempts) if `--n-types` is outside `[2, capacity]`; fails
    with an actionable message (not a silent `None`) if zero attempts came back solvable.
- Deliberately NOT exhaustive — a fast mid-design probe ("does this layout even reach Extreme"), not a
  replacement for `templates/difficulty_minmax_solvable_parallel.py`'s full per-tile_count CSV sweep
  (which still scores with the OLD `final_score`, a separate gap not addressed here).
- Documented in `SKILL.md` next to the `n_types` range rule it complements.

**Caught by a follow-up audit before this shipped, and fixed in the same version** (a subagent asked
to independently verify the calculation logic, running real code rather than trusting the
implementation): a flat, fixed sample count per `n_types` under-sampled exactly the endpoint that
matters most for MAX — higher `n_types` solves less often (harder board), so `n_types=20` regularly
came back with 0-1 solvable samples out of 3 while `n_types=10-15` filled easily, making the reported
MAX look ~30 points lower than what the layout can actually reach (confirmed: 98.13 reported vs 130.37
achievable on a real layout). Fixed with **adaptive per-point sampling** (keep retrying a point, up to
a bound, until `--samples` solvable hits land or a GLOBAL `--time-budget` is spent) plus a new
`per_n_types` field in the result reporting solvable/tried per point and a `timed_out` flag, so a
caller can see when a number is under-supported instead of trusting a silently-thin sample. The
retry-until-success fix is itself slower, which pushed wall-clock on a large layout to 39s against a
15s budget with the original `--v3-cap 30000` default — lowered the default to **15000** (tuned against
real measurements, not guessed: 30k let a single solve_v3 call dominate the whole budget by itself; 5k
was too cheap to ever prove a board solvable near `n_types=20`, i.e. zero signal, not just slower).
Net effect: typical/small layouts (capacity ~13-24) stay fast; large/deep ones (capacity 40+) may still
run somewhat past the nominal 15s (a single already-started solve_v3 call can't be interrupted) or come
back with an honestly-flagged thin sample at the high end — both documented in the script's docstring
rather than smoothed over.

## 0.9.3 — memory/plugin-doc parity audit

Prompted by a real symptom: an agent forgot the "tile ids must come from a fixed set" rule mid-work.
Root cause: that rule (and one other, the bonus-circular-collision shape) lived only in the operator's
private cross-session memory + a code comment — never written into the plugin's own docs, so any
fresh agent/subagent/other machine invoking the skill had no way to see it. Both were added to
`reference/game_rules_and_bugs.md` (see the commit right before this one).

Followed with a full audit: all ~26 memory entries checked against the plugin's actual `.md` files
(4 parallel agents, one per batch, each re-verifying against live code rather than trusting the
memory text). Result: most were already documented; 3 more real, load-bearing gaps found and fixed —

- **`reference/solver_pruning_history.md`** (new) — which solver pruning ideas are proven unsound
  (atomic-triple collapse for existence queries, tray-submultiset dominance) vs theoretically sound
  but unimplemented (POR local-independence), and why. Existed only as a literature-survey memory;
  nothing stopped a future agent from re-attempting a pruning already known to be wrong.
- **`gen-layout/SKILL.md` §4b** (new) — the "quality beats throughput" bar for every layout (solvable
  always, symmetric, cells ~48–126/layers ~2–7, reject lopsided/sparse, prefer parametric over
  icon→pyramid). Previously only stated as the historical justification for retiring bulk mode, not
  as a standing rule for ongoing single-layout generation.
- **`docs/CLAUDE.md`** (new intro section) — "scripts here are agent-consumed, not human-typed" design
  philosophy (prioritize speed/determinism/machine-readable output/actionable failures). Existed only
  in a changelog entry (historical, not a standing instruction) and in memory.

Also fixed two smaller doc gaps (`gen-layout/SKILL.md` §9: `layout_diff` 0–12 is a different, tile-free
scale from `new_diffScore` 0–190 — was easy to conflate) and two stale memory entries that no longer
matched the repo (a resolved "untracked file" warning; a pre-plugin-migration directory map) — updated
in place rather than left to mislead a future session.

## 0.9.2 — new rule: n_types range (10–20, ±2 for extreme difficulty)

New design rule, requested directly: every level should have **10–20** distinct tile types
(`n_types` — special 1001/1002 collapse to 1 bucket, per the existing `new_diffScore` definition).
An extreme difficulty target may push this to **8–22**, never further — `n_types` is the strongest
lever on `new_diffScore` (+2.897/type per §4.1), so it's the easiest knob to over-push past what the
score is actually asking for.

- Documented at the source of truth: `TileLevel_AI_KnowledgeBase.md` §4.4 (new section, next to the
  `new_diffScore` formula it derives from).
- Propagated into the plugin: `tile-level-design/SKILL.md`, next to the `new_diffScore` tier table.
- `analyze_level.py` now prints a warning when a level's `n_types` falls outside 8–22 (hard) or
  10–20 (soft, still within the ±2 extreme-difficulty band) — visibility only, not a hard-fail (this
  is a design guideline, not a structural impossibility like the ÷3 rule).

## 0.9.1 — plugin size reduction (no behavior change)

Housekeeping only, prompted by a bloat check ("plugin có đang phình to không?"): the plugin was
14MB, 41% of it a single CSV.

- **`winrate-target/Note - Layout.csv` (5.7MB) → `layout_cells.json` (2.7MB, 53% smaller).**
  `_load_layout_cells()` was confirmed (grep, only call site in the whole plugin) to read just two
  columns — `layoutId` and `slotsJson`, and from `slotsJson` only each stone's `x`/`y`. Extracted a
  compact `{layoutId: [{"cells":[{"x","y"}]}]}` map ahead of time; verified byte-identical output
  against the old CSV-parsing logic on a 30-layout random sample (all 1501 distinct layoutIds
  preserved) plus a live import of the updated function. `Note - Layout.csv` removed.
- **`tile-level-design/templates/` (21 scripts) → 17 top-level + 4 archived.** Moved
  `find_hybrid_custom.py`, `difficulty_minmax.py`, `difficulty_minmax_combined.py`,
  `gen_5_patterns.py` into `templates/_archive/` — each has a *confirmed* successor (not a guess):
  `find_hybrid_custom_fast.py`'s own docstring states it fixes `find_hybrid_custom.py`'s bottleneck
  (and `gen_all_9.py` already calls the `_fast` one); `docs/CLAUDE.md` §4 already names
  `difficulty_minmax_solvable_parallel.py` as canonical over the other two; `gen_5_patterns.py` is
  functionally absorbed by `scripts/gen_pattern.py --pattern N` and wasn't cited as an active
  recommendation in any doc. Left everything still depended on by `gen_all_9.py` or recommended
  in an active user-phrase-mapping table untouched, rather than guess at equivalence (e.g.
  `find_easy_first_half.py`'s window-metric is called out as "preferred" in
  `solver_infrastructure.md` — not touched without verifying `gen_pattern.py --pattern 2` matches
  it exactly, which wasn't done this pass).

## 0.9.0 — skill boundary hardening, generation-pipeline race fix, greedy-vs-exact conclusion

Four fixes reported from real usage, each investigated with direct source evidence (not speculation)
before being fixed. Behavior-changing — not a pure perf release.

**Plus a documentation-hygiene pass** enforcing the project's "sửa = xoá câu sai, không viết đè" rule
(a correction must delete/replace the wrong sentence, never leave it standing next to the new one —
an old-but-"close enough" sentence otherwise gets propagated into future decisions via
experience-following). Two independent audits (SKILL.md ×4 + `docs/`, and `reference/*.md`) found 21
instances of stale facts left in place after a correction elsewhere, since fixed: a stale `cover100`
formula description (2 files) contradicting the shipped area-based engine code; `display-json-level`
describing Cloud's reveal behavior under the Mystery bullet (and missing the `o` field entirely); wrong/
superseded script names (`find_hybrid_fast.py` where `find_hybrid_priority_v2.py` is correct; `find_*.py`
template routing surviving in 4 places after `gen_pattern.py` superseded them); a wrong deprecated
`final_score` formula (missing a whole component, wrong weight) presented with no deprecation note in
`docs/CLAUDE.md` and `docs/LEVEL_DESIGN_GUIDE.md`; disagreeing row-counts/layout-counts/canonical-script-
names between `docs/CLAUDE.md` and `SKILL.md` (ground truth); `SKILL.md §18`'s own index missing a row
for `greedy_vs_exact.md`; an `INDEX.md` claim ("now 6 patterns") the target file doesn't back up; a
wrong section citation in `greedy_vs_exact.md` itself. `docs/LEVEL_DESIGN_GUIDE.md` (a 364-line guide
built around a THIRD pattern-numbering scheme, T1-T5) was found out-of-scope of both audits and is now
flagged historical/unverified pending its own pass, rather than left silently authoritative-looking.
Three items were deliberately left unfixed as genuine product judgment calls, not auto-resolved:
`bridge_distribution.md`'s 3- vs 4-group model, `guided_trap.md`'s fail-rate criterion vs SKILL.md §4's
definition, and `level_design_patterns.md`'s pattern-numbering scheme (renumber vs. names-only).

**A second, adversarial re-audit (run actual code, not just read it) then caught what the first pass
missed:** two more `find_*.py` templates (`find_hybrid_priority_v2.py`, `find_hybrid_cascade_L21.py`)
still wrote a hardcoded, non-seed-unique filename — the exact write-race the fix was supposed to
eliminate everywhere, missed because they don't match the `*_candidate.json` pattern the original sweep
grepped for. Now fixed (`*_verified_s{seed}.json`), bringing all 15 `find_*.py` templates to the safe
convention (verified by direct grep of every `open(...json...)` write site, not just the ones named in
the original fix). `reference/difficulty_design_workflow.md` still taught the old racy "kill other
workers" flow as the approved workflow — corrected to match `docs/CLAUDE.md §6`. Also fixed:
`reserve_special.py::_gen_normal_level` was missing the `board is None` guard its sibling
`gen_pattern.py::_load_trimmed` has (a relative path crashed with a raw traceback instead of a clean
error); `SKILL.md §22b` overstated that `reserve_special.py` renames an output `layout` field (it has
no such field — only `gen_pattern.py` does); `analyze_level.assert_geometry_unchanged`'s error message
pointed to a doc heading string that didn't exist. Three citation line-numbers in `greedy_vs_exact.md`
had already drifted from a subsequent edit — replaced with function/section names so they can't drift
again. Verified via 3 independent adversarial audit agents that actually ran the code (not just read
it) — Task 3 and Task 4 reproduced clean (SOLID); Task 1 and Task 2 each had real gaps, now closed.
Full regression suite re-run clean after all fixes: 55-board solver oracle bit-identical,
`test_special_solver.py` 14/14, gen-layout `test_full.py` 14/14, `claude plugin validate` passing.

- **Geometry can no longer drift silently during tile assignment (breaking default change).**
  `gen_pattern.py`/`reserve_special.py` used to silently drop up to 2 cells when a layout wasn't ÷3,
  still exporting under the ORIGINAL layout's name — a real "Layout_A silently becomes Layout_A1" bug,
  inconsistent with `find_hybrid_fast.py`'s existing hard-fail behavior for the identical precondition.
  Both now **hard-fail by default**; pass `--allow-trim` to explicitly opt in, which records
  `metadata.geometry_trimmed` and renames the output layout (`L20+trim1`, never bare `L20`). New
  reusable guard: `analyze_level.assert_geometry_unchanged(before, after, context)`. New governance
  text in both `gen-layout/SKILL.md` and `tile-level-design/SKILL.md` (§22b): don't blend
  geometry-editing and tile-assignment into one operation, and a loaded layout's cell set is frozen
  for that operation unless a step (stacks, specials) is explicit and documented.
- **Fixed a real parallel-worker write race (not a solver bug).** `docs/CLAUDE.md` §6 mandated 8
  workers write to a SHARED `*_candidate.json` filename ("first success wins, kill the rest") —
  directly contradicting its own §247 "unique output files per worker" rule. `find_trap_fast.py`,
  `find_trap_70_90.py` (worst — a filename hardcoded across ALL layouts and seeds), and 8 other
  `find_*.py` templates now write `*_s{seed}.json`. §6 rewritten: workers write unique files, the
  orchestrator waits for all of them and independently re-verifies each file before picking a winner
  — eliminates the race at the root rather than mitigating it. (Solver transposition tables were
  investigated and confirmed 100% call-local — cross-board memo leakage was ruled out as a cause.)
- **`solve_v3` now rejects malformed boards immediately instead of silently misreporting.** A NORMAL
  board (no specials) with `total_cells % 3 != 0` can never fully clear — this is always a caller bug,
  never a real "maybe unsolvable" case. `solve_v3` now raises `ValueError` before spending any DFS
  time (both engine copies — `gen-layout/engine/` and `tile-level-design/engine/`, kept byte-parity).
  Verified bit-identical on the 55-board oracle (the guard never fires on any well-formed board).
- **New `scripts/solve_dispatch.solve_any(board, ...)`** — inspects a board for bonus/mission stones
  (`i>=1000`) and calls the right solver (`solve_v3` vs `solve_special.solve_v3_special`) automatically.
  Additive — existing direct call sites are unchanged. Recommended default for new code that isn't
  already certain of its board type.
- **New `reference/greedy_vs_exact.md`** consolidates the 4 mechanisms that touch "greedy vs exact"
  (the stochastic `playout()` evaluator, the exact per-step `min_safe_choices` probe, the solver-internal
  atomic-triple collapse, and the deprecated `TileSolver.analyze`) into one decision table — what each
  is for and what it must NOT be used for (citing the documented empirical failure of greedy-fail-rate
  as a *general* difficulty metric, valid only for its narrow "trap ẩn" purpose).
- **New `analyze_level.py --solve-profile`** persists the first real joint conclusion combining both
  solving methods: `metadata.solve_profile = {"dfs_solvable", "greedy_fail_rate", "classification"}`,
  classification ∈ `hidden_trap`/`partial_trap`/`straightforward`/`unsolvable`/`None` (reuses the
  existing 0.90/0.20 thresholds from `hidden_trap_levels.md`, no new thresholds invented). **Off by
  default** (300-playout cost not paid on the common path). Explicitly NOT a difficulty ranking metric
  — same scoping discipline as `min_safe_choices`, never replaces `new_diffScore`. Verified against the
  documented `trap_an_L20_s82.json` reference case (reproduces `classification=hidden_trap`,
  `greedy_fail_rate≈1.0`) and unit-tested at all classification-boundary values.

## 0.8.2 — `parallel_sweep` helper: parallelize a seed/candidate sweep, keep serial semantics

- **New `skills/tile-level-design/scripts/parallel_sweep.py`.** `first_match(worker, items, predicate, …)`
  runs a top-level picklable `worker(item)` across CPU cores and returns the **lowest-index** item whose
  `predicate(result)` is True (ordered early-stop) plus the results seen up to it. The winner is
  deterministic — it does NOT depend on which worker finishes first — so parallelizing a seed/candidate
  sweep accepts the SAME item a serial `for…: if ok: break` would, ~N× faster on N cores. This is the
  generic core so the correctness invariants live in one tested place (verified: lowest-index winner
  under scrambled finish order, parallel == serial match+seen, deterministic across runs).
- **Guards non-reproducibility:** refuses to run unless `PYTHONHASHSEED` is pinned (spawned workers
  reproduce serial results only when hash randomization is fixed), overridable for hash-independent workers.
- Intended for the bulk/target-difficulty search: parallelize the per-seed generation sweep. Pure
  orchestration — the accepted level is still exact-verified (solvable + on-target), not a quality trade.
  (The project-side glue that binds it to `generate_one` stays project-side; it imports project pipeline
  code and can't be a self-contained plugin script.)

## 0.8.1 — `solve_v3_special` incremental compute_pickable (~4× on hard special boards, exact)

- **`solve_special.solve_v3_special` now threads the pickable mask instead of rescanning O(active) each
  node.** Removing a tile — or a whole `auto_clear` cascade of specials — can only newly EXPOSE the tiles
  it covered (`blocks[i]`); nothing already pickable becomes un-pickable. A new `_expose_set` helper
  updates the mask for exactly those, so `compute_pickable` is no longer recomputed from scratch at the
  node entry, inside the `auto_clear` cascade, and on every regroup after an atomic collapse. This matters
  more than in the normal solver (which rescans in one place): **measured ~4× on hard special boards**
  (e.g. an unsolvable L30_Mission that exhausts 55k expansions: 2.47s → 0.60s), directly attacking the
  special-solver cost that dominates special-level generation.
- **Exact by construction** — the pickable mask is *computed* incrementally, the search tree is unchanged.
  Verified bit-identical `(status, depth, expansions)` on the 55-board regression oracle (incl. 7 special).
- The normal engine `solve_v3` (`verify_smart_v3.py`) is unchanged; the same technique could be applied
  there for normal-board gates as a follow-up.

## 0.8.0 — `min_safe_choices` difficulty probe now in the plugin (~2× faster, exact)

- **New script `skills/tile-level-design/scripts/min_safe_choices.py`.** The "one wrong move = instant
  loss" probe — walks the first `check_depth` steps of a proven winning path and counts how many of the
  currently-pickable moves are *safe* (still lead to a winnable state); `min_safe == 1` while
  `total_pickable > 1` is the bottleneck. Previously this lived only in project-side pacing tooling, so
  pulling the plugin never sped it up; it is now distributed and importable
  (`from min_safe_choices import min_safe_choices, count_wins_capped`) with a machine-readable CLI.
- **Its `winnable()` existence oracle carries two verified-EXACT optimizations** that do NOT alter the
  search tree (they explore the same exhaustive DFS, only cheaper per node): (1) tsize threading —
  carry the running tray size instead of re-summing; (2) incremental `compute_pickable` — re-test only
  the tiles a pick uncovers. **~1.8× over the tsize-threaded form alone, which is itself ~2× over a
  plain re-summing DFS** (measured separately; not benchmarked end-to-end as one figure). Verified
  0-divergence vs an exhaustive DFS across 9 `PYTHONHASHSEED` sweeps (~1900 boards) and end-to-end
  `(safe, step, total)` identical to a naive implementation.
- **NO atomic-triple collapse — by design.** Every triple-forcing collapse (solve_v3's full atomic AND
  the "narrow" `== needed` variant) is UNSOUND for this arbitrary-mid-state existence query: it commits
  to completing a triple first and short-circuits, which can miss a win that must start with a different
  type (over-prune → wrongly flags a safe move as a trap → wrong difficulty). The narrow form passed a
  53-board gate but was then caught over-pruning by a hash-seed sweep; do not re-add any collapse.
- **NORMAL boards only:** raises on boards with special tiles (`i≥1000` auto-clear — use
  `solve_special.solve_v3_special`). `count_wins_capped(board, cap=2)` keeps the original signature and
  gets tsize threading only. Self-contained: builds its own 1×1-box `blocked_by` (or accepts one).

## 0.7.3 — solve_v3 tray-size threading (zero behavior change)

- **`solve_v3` runs ~2.5× faster** by threading the running tray size through the DFS instead of
  re-summing the packed tray on every node. `tray_size(tray)` was an O(n_types) loop called at each
  expansion and each atomic pass; now the size is carried as a `tsize` argument and adjusted by ±deltas
  (atomic triple: `-existing`; branch pick: `-2` on a completing triple, `+1` otherwise). Applied to the
  engine solver (both `gen-layout` and `tile-level-design` copies, byte-identical) and to
  `solve_special` (hand-mirrored). **Verified bit-identical:** a 55-board regression oracle (normals +
  bonus/mission specials, at a 300k cap) returned identical `(status, depth, expansions)` for every
  board — pure speed, no change to which levels are judged solvable.

## 0.7.2 — bonus circular collider + stack rendering + art-id remap

- **Bonus (1001) collides as a CIRCLE, not a box** (confirmed against the live game; the box test
  over-covered the four corners). Every overlap pair involving a bonus now uses `dx²+dy² < (ha+hb)²`;
  mission (1002) and normal↔normal stay square (AABB). Fixed in `solve_special._build_visibility_2x2`,
  `make_play_html.overlaps()`, and `reserve_special`'s coverage/separation gates. **Correctness fix:** a
  regression oracle over 55 boards changed exactly 2 (both bonus) — one flipped `unsolvable → solvable`
  (a real game-solvable level the box test wrongly rejected by hiding a start triple), the other solved
  faster; all normals + non-corner bonus boards unchanged. Designer spec §1.3 updated.
- **Preview renders `stacks[].stones`.** `make_play_html` only read `layers[]` and silently dropped every
  tile in a stack pile (~1/5 of reference levels store real tiles there). Now promoted to synthetic
  layers above the normals (top-of-pile pickable), matching the solver's build convention.
- **Real Group_1 art-id remap.** `VALID_GROUP1_IDS = [85] + range(142,171)` (the 30 shipped art ids).
  `gen_pattern.py` now remaps its sequential type ids onto these by default (bijective per-level relabel,
  no effect on difficulty/solvability) so generated levels render with real sprites; `--raw-ids` opts out.

## 0.7.1 — level-gen speed (zero behavior change)

Optimizes generation wall-clock; the delivered levels are unchanged in quality (every level still
verified v3-solvable). Profiling showed `solve_v3`/`solve_v3_special` (~0.8–1.5s/call) dominates the
rejection-sampling loop; everything else (TEEngine gen 1ms, scorer 49ms, greedy 97ms) is noise.

- **`gen_pattern.py`: cheap gates BEFORE the expensive solve.** The greedy fail metric (P1) and the
  structural top-half check (P2) now run before `solve_v3`, so failing candidates skip the solve
  entirely → P1/P2 ~13–32s → ~1–2s (~10×). Same acceptance criteria, so output quality is unchanged.
- **`gen_pattern.py`: `--workers N`** — optional multiprocessing (default 1) that splits the attempt
  budget across processes; first hit wins. For genuinely slow searches (hard targets, custom patterns).
- **`reserve_special.py`: dropped the redundant in-loop 2M solve.** The 200k pass already proves
  solvability (True comes fast); the old 2M pass only ran on already-True boards → pure waste that cost
  ~60s per unsolvable candidate. **Outcome-identical.**
- **Solver dedup (`verify_smart_v3.py` ×2 copies + `solve_special.py`):** the atomic-triple collapse
  recomputed `compute_pickable` + the type grouping on its first pass even though the values were just
  computed one line above. Now reused → **solve_v3 ~34% faster** (1150→755ms). Verified **bit-identical**
  `(status, depth, expansions)` over a 55-board oracle (solvable / unsolvable / cap-hit, incl. specials);
  engine byte-parity intact; `test_special_solver.py` 14/14.

## 0.7.0

- **New `scripts/gen_pattern.py` — ONE parameterized tool for all 6 design patterns (SKILL.md §4) on ANY
  layout.** Replaces the per-layout one-off research templates (`find_trap_fast` / `find_easy_*` /
  `find_bridge_L21` / `find_clear50_trap` / `find_guided_trap_L21`), which were pinned to L20/L21/L50 and
  are kept in `templates/` as provenance. Every hardcoded geometry constant is now derived from the given
  layout (top-half / 3-band partitions, the `6a+3b=n` easy/trap config solver).
  - `--pattern 1..6 --layout <id|path>`: 1 trap (player fail-rate, `--metric greedy|random`), 2 easytop
    (structural top-half triple-frac), 3 bridge (easy + recurring bridge types + trap zones), 4 clear50
    (easy-top/trap-bottom, greedy clears a target band), 5 guided (steep top-band gradient), 6 score
    (score band only).
  - The 6 duplicated greedy-playout copies are consolidated into one `playout(mode='greedy'|'random')`
    metric. Greedy is an EVALUATOR (filter stage), never a generator.
  - Score gate is OFF by default (per-layout-tuned bands rejected ~everything elsewhere); enable with
    `--score-min/--score-max`. `--attempts` (default 2000) is a rejection-sampler budget.
  - P4/P5 (custom clear-target) are geometry-sensitive: they hit the clear band on layouts with depth,
    else return a **best-effort** level (metadata `in_band` + `note`), and honestly report "no candidate"
    on degenerate (e.g. 2-layer) layouts. P1/P2/P3/P6 generalize cleanly. All patterns verify v3-solvable
    and emit game stones format.
- **Cleanup:** removed 3 superseded difficulty-sweep artifacts (`data/difficulty_minmax_strategy.csv`,
  `templates/difficulty_minmax_strategy_parallel.py`, `templates/difficulty_minmax_custom.py`) — replaced
  by the kept `difficulty_minmax_combined.*` / `difficulty_minmax_solvable_parallel.py`; verified 0 code
  imports and 0 doc references before removal (~254K).

## 0.6.0 — new skill `winrate-target` (design by REAL-PLAYER metric)

Purely **additive**: the three existing skills are untouched (byte-identical to 0.5.4). Adds a fourth
skill for a different question.

**What it answers.** The other skills answer *"give me the shape/level I have in mind"* and score the
board's **static** difficulty (`diffScore`). `winrate-target` answers *"give me a level where REAL
PLAYERS behave like X at stage Y"* — e.g. *"a symmetric level whose first-attempt win rate is 87% at
late"*, or *"keep layout 54's shape but make booster usage ~17% at early"*.

**How.** A 3-layer model fitted on real play logs (508k plays, 28,750 players, 790 levels):

1. `beta` — intrinsic board difficulty from 36 features (10 static + 26 from bot simulation).
2. **Survival Theta** — the player-skill distribution at that exact level position, via the inverse
   Mills ratio of the survival funnel. Uses `E[sigmoid(theta - beta)]`, *not* `sigmoid(mean theta)`
   (Jensen's inequality: the naive version pushes MAE to 16.4).
3. Residual heads for 9 metrics — Ridge (alpha per head by cross-validation) plus Gradient Boosting
   where CV shows it genuinely wins (currently 7/9 heads). Ridge coefficients stay in the JSON as an
   inspectable fallback if `heads_gbm.joblib` is missing or built by another sklearn version.

**Nine metrics.** `win_rate` (first attempt) · `win_att` · duration · `revive` · `booster` ·
`near_miss` · `undo` · `shuffle` · `magnet`.

**Refuses to extrapolate — on purpose.** Generation is seeded from real levels near the target and
constrained to their feature bounds. When a target lies outside the observed distribution the tool
reports `KHONG DAT MUC TIEU` rather than inventing a confident number. (Demonstrated: forcing the
linear head to beta=+20 predicts *131% of players use a booster* — the guard exists to stop exactly
that reaching a designer.)

**Honest limits** (see `skills/winrate-target/SKILL.md` §6):

- `booster`/`revive` measure **item-usage rate**, not revenue — the logs contain no purchase events.
- Four metrics are still unreliable at `late` (`undo`, `near_miss`, `shuffle`, `magnet`).
- The `[N]` skill-level slot only affects `win_rate`/`win_att`/`near_miss`; the six linear heads
  ignore it.
- Layer 1 (`beta`) is deliberately **never** recalibrated — it is the fixed measuring stick that
  keeps designs comparable across cohorts. Only theta and the heads are refitted.

**Tooling.** `scripts/recalibrate.py` refits the model from a raw cohort CSV (`--dry-run` prints a
before/after MAE table first); `scripts/eval_cohort.py --check-drift` scores the current model against
other cohorts and writes a drift status that every CLI run then surfaces as a banner.

Verified before merge: `tests/check_engine_parity.py` passes; the new skill borrows
`skills/gen-layout/engine` (no third engine copy); `gen`/`target`/`info` all run from the new path.
The 0.5.4 `n_types` change (specials collapsing to one bucket) does **not** affect this model — 0 of
the 939 cached levels contain specials, and generation excludes specials from the count.

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
