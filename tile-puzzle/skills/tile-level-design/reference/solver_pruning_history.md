---
name: Solver pruning — what was tried, what's proven unsound, what's still open
description: Before attempting ANY new node-reduction pruning for solve_v3/winnable/min_safe_choices — read this first, it's a record of what already failed and why
type: reference
---

Full-information ("with peeking") Mahjong-solitaire is **NP-complete** (de Bondt 2012, arXiv:1203.6559,
base attributed to Eppstein; hidden-info variant is PSPACE, Condon et al.). This game is full-info +
3-matches + a 7-tray resource — NP-complete regime by strong analogy (no paper covers the exact
tray-triple variant). **Implication: no polynomial exact algorithm exists — pruning + move ordering +
parallelism is the only lever, and every pruning candidate needs a real soundness argument before it
ships**, not just "passed on my test set."

## Proven UNSOUND — do not re-attempt without new evidence

**Atomic-triple collapse for existence queries** (`winnable`/`min_safe_choices`, NOT the DFS-internal
optimization inside `solve_v3` which is a different, sound use — see `reference/greedy_vs_exact.md`):
taking a forced-looking triple immediately, instead of branching, is an attempted
*stubborn/persistent set that isn't persistent* (Partial-Order Reduction theory — Valmari 1991 stubborn
sets; Bønneland et al. arXiv:1912.09875 licenses POR for reachability games). Soundness needs every move
outside the reduced set to be INDEPENDENT (commute + mutually non-disabling) of moves inside it. Taking a
triple violates both: it consumes shared tray slots, and removes tiles a different first-move might have
needed. This is not a hunch — it was caught concretely by a PYTHONHASHSEED sweep after passing a fixed
53-board test set clean. **Any pruning technique that touches the search tree must be swept across
multiple PYTHONHASHSEED values, not just validated on one fixed board set** — a fixed set can hide
rare-but-real over-pruning. Full experimental writeup: `_haul/winnable_atomic_INEXACT_proof.md`
(external to this plugin, kept as historical evidence).

**Tray-submultiset dominance** (Torralba IJCAI'18-style state dominance): the claim would be "same
remaining board + tray_A ⊆ tray_B ⟹ state B can be discarded." **Judged UNSOUND for this game**: win =
board-empty (tray residue at the end is irrelevant), but triple-completion changes the tray
NON-monotonically mid-play — state B with 2×X completes a triple on the next X-pick and clears 3 tiles,
while state A with 0×X just banks 1 — so the ⊆ invariant breaks before the game ends and neither state
cleanly dominates the other. Same failure shape as atomic collapse. Do not implement without a rigorous
proof, and even then, sweep hash seeds before trusting it.

## Theoretically sound but unimplemented — a real option, not yet done

**POR local-independence**: fix the pick order of two moves ONLY when they are region-disjoint AND
neither completes a triple AND the tray isn't near-full. Genuinely commuting moves under those three
conditions, so this one is theoretically clean (unlike the two above). Not implemented — complex, and
payoff is uncertain. If attempted, it needs the same proof + PYTHONHASHSEED-sweep discipline as
everything else here before it ships.

## What actually shipped (safe, exact-by-construction, changes cost per node — not the tree)

`tsize` threading + incremental `compute_pickable` — variant C. Ships as `winnable()`/
`min_safe_choices.py` (0.8.0) and `solve_v3_special` (0.8.1, ~4× on hard special boards). No pruning of
the search tree at all — just cheaper per-node bookkeeping, so it can't introduce the
over-pruning failure mode above by construction.

**Bottom line for anyone tempted to speed up the solver further**: parallelism (transposition-driven
search, lockless TT, work-stealing DFS) is the reliable remaining wall-clock lever. Any further
*pruning* idea must clear the bar above — proof of independence, then a hash-seed sweep — before it's
considered for `solve_v3`, `solve_v3_special`, or `winnable`.
