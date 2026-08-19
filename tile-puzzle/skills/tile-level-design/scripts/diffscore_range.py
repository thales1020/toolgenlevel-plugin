"""diffscore_range.py — achievable new_diffScore range for ONE layout, FAST (agent-callable).

Input: a layout (bare id like 'L20', filename, or path — same resolution as gen_pattern.py). Output:
the min/max new_diffScore (docs/HANDOFF_KNOWLEDGE.md sec.4.3, the RANK metric — see diff_score.py)
achievable via random tile assignment, SOLVABLE boards only.

Two modes:
  --n-types N   : sweep only N types. Reports min/max new_diffScore across `--samples` solvable
                  attempts at that N.
  (omitted)     : sweep representative points across the design rule's DEFAULT range 10-20
                  (TileLevel_AI_KnowledgeBase.md sec.4.4 / SKILL.md — "every level should have 10-20
                  distinct tile types"), clamped to this layout's capacity — checks 10, a midpoint, and
                  20 (clamped), not every value in between, to stay fast. Reports the GLOBAL min/max
                  across all points swept, plus which n_types achieved each.

  CAUGHT BY AUDIT (fixed): higher n_types has a LOWER solvable rate, so a flat `samples` attempts per
  point under-samples exactly the endpoint (20) that matters most for MAX — the reported max was seen
  ~30 points below the true achievable max on a real layout. Fixed with adaptive per-point sampling
  (below) instead of a flat attempt count; `per_n_types` in the result reports solvable/tried per point
  so a caller can judge how well-supported each number is.

This is a FAST PROBE meant for an agent asking "can this layout hit my difficulty target" mid-design —
not an exhaustive sweep. `time_budget_s` (default 15s) is a SOFT target: it stops new attempts from
starting once elapsed, but can't interrupt one already running, so on a large/deep layout a single
solve_v3 call near the top of the n_types range can push wall-clock a bit past it (measured: ~16s on a
typical 72-cell layout, well over a minute if you raise --v3-cap back toward the 30k+ used elsewhere).
Validated fast (<1s) on small/typical layouts (capacity ~13-24); larger ones (capacity 40+) may exceed
the nominal budget and/or come back with `per_n_types` showing 0 solvable at the high end — both are
reported transparently, never silently absorbed into a wrong number. For a thorough per-tile_count CSV
over ALL layouts, use templates/difficulty_minmax_solvable_parallel.py instead (note: that one still
uses the OLD final_score/chaos-score, not new_diffScore).

Usage:
  python diffscore_range.py <layout> [--n-types N] [--samples 3] [--v3-cap 15000]
    [--time-budget 15] [--seed 1] [--out o.json]

Output (stdout + optional --out JSON):
  {"layout": "L20", "capacity": 24, "n_types_swept": [10, 15, 20],
   "per_n_types": {10: {"solvable": 3, "tried": 3}, 15: {"solvable": 3, "tried": 4},
                    20: {"solvable": 3, "tried": 11}},
   "min": {"new_diffscore": 12.3, "tier": "Easy", "n_types": 10, ...},
   "max": {"new_diffscore": 58.1, "tier": "Very Hard", "n_types": 20, ...},
   "samples_solvable": 9, "samples_tried": 18}
"""
import sys, os, json, argparse, random, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")
sys.path.insert(0, ENGINE)
sys.path.insert(0, HERE)
from tile_level_simulator import TEEngine, load_board_from_file, load_scoring_weights
from verify_smart_v3 import solve_v3
from diff_score import compute_new_diffscore, tier as _tier
from gen_pattern import _resolve_layout   # same bare-id/filename/path resolution as gen_pattern.py

DEFAULT_RANGE = (10, 20)          # SKILL.md / TileLevel_AI_KnowledgeBase.md sec.4.4
V3_CAP_DEFAULT = 15_000           # smaller than the 50k/100k used elsewhere; tuned (not guessed) against
                                   # TIME_BUDGET_DEFAULT below -- 30k let a single solve_v3 call on an
                                   # unsolvable high-n_types board run past the whole time budget by
                                   # itself (measured 39s on a real layout vs a 15s budget); 15k keeps
                                   # total wall-clock close to budget while still landing real solvable
                                   # samples at the high end (5k was too cheap to prove ANY solvable
                                   # board near n_types=20 on the same layout -- 0 signal, not just slow)
SAMPLES_DEFAULT = 3
TIME_BUDGET_DEFAULT = 15.0        # global wall-clock cutoff across the whole sweep (see diffscore_range)


def _one_attempt(layout_path, n_types, seed, v3_cap, weights):
    """Generate ONE random solvable-checked board at n_types types. Returns the new_diffScore dict,
    or None if this attempt wasn't solvable / didn't hit n_types exactly."""
    random.seed(seed)
    board = load_board_from_file(layout_path)
    if board is None:
        raise SystemExit(f"could not load layout from {layout_path} (absolute path required on Windows)")
    eng = TEEngine()
    eng.validate = False
    eng.color_count = n_types
    cells = board.all_cells()
    if n_types > len(cells) // 3:
        return None   # over capacity, don't bother generating
    if len(cells) > 6:
        eng.style_mode = 3
        eng.extended = True
    elif len(cells) > 5:
        eng.style_mode = 7
    eng.generate(board)
    actual = len({c.tile_id for c in board.all_cells() if c.tile_id >= 0})
    if actual != n_types:
        return None
    solved, _depth, _exp = solve_v3(board, max_expansions=v3_cap, verbose=False)
    if solved is not True:
        return None
    is_mystery = 0   # plain boards only -- this probe doesn't place specials/mystery
    score, s, nt = compute_new_diffscore(board, weights, is_mystery)
    return {"new_diffscore": round(score, 2), "tier": _tier(score), "n_types": nt,
            "intra_group": round(s["intra_group"], 2), "cover100": s["cover100"]}


def diffscore_range(layout, n_types=None, samples=SAMPLES_DEFAULT, v3_cap=V3_CAP_DEFAULT, seed=1,
                     time_budget_s=TIME_BUDGET_DEFAULT):
    """Core function. `layout` = bare id / filename / path. `n_types` = fixed value, or None to sweep
    the design rule's default 10-20 range (clamped to capacity). Returns the result dict described in
    the module docstring. Raises SystemExit with an actionable message if NO attempt (at any swept
    n_types) came back solvable -- never returns a silently-empty/None result.

    `time_budget_s` is a GLOBAL wall-clock cutoff across the whole sweep, not per-point -- adaptive
    per-point sampling (below) can otherwise blow way past the "fast" contract on a large/hard layout
    (a real layout with capacity 42 took 47s before this cutoff existed). Once the deadline passes, no
    new attempts start; whatever solvable results already landed are used, and `per_n_types` still
    reports which points came up short so the caller can see it."""
    layout_path = _resolve_layout(layout)
    probe = load_board_from_file(layout_path)
    if probe is None:
        raise SystemExit(f"could not load layout from {layout_path}")
    total_cells = probe.total_cells()
    capacity = total_cells // 3

    if n_types is not None:
        if n_types > capacity or n_types < 2:
            raise SystemExit(
                f"diffscore_range: n_types={n_types} is out of range for layout {layout} "
                f"(capacity={capacity} = {total_cells} cells // 3, min 2) -- no attempt would ever "
                f"be solvable at this n_types, not even trying.")
        candidates = [n_types]
    else:
        lo, hi = DEFAULT_RANGE
        mid = (lo + hi) // 2
        candidates = sorted({max(2, min(v, capacity)) for v in (lo, mid, hi)})

    weights = load_scoring_weights()
    results = []
    tried = 0
    per_n_types = {nt: {"solvable": 0, "tried": 0} for nt in candidates}   # pre-seed so a point
    # skipped entirely by the time-budget cutoff still shows up as 0/0, not silently absent.
    # Adaptive per-point sampling: higher n_types solves less often (confirmed by audit — a flat
    # `samples` attempts starved the top endpoint, the one that matters most for MAX). Keep trying,
    # up to a bounded budget, until `samples` solvable hits land for THIS point, or the budget runs out.
    max_attempts_per_point = samples * 4
    deadline = time.time() + time_budget_s
    timed_out = False
    for nt in candidates:
        solvable_here = []
        attempts_here = 0
        for s in range(max_attempts_per_point):
            if len(solvable_here) >= samples:
                break
            if time.time() > deadline:
                timed_out = True
                break
            attempts_here += 1
            tried += 1
            r = _one_attempt(layout_path, nt, seed * 100_000 + nt * 1000 + s, v3_cap, weights)
            if r is not None:
                solvable_here.append(r)
        per_n_types[nt] = {"solvable": len(solvable_here), "tried": attempts_here}
        results.extend(solvable_here)
        if timed_out:
            break   # don't start a fresh candidate once the global budget is spent

    if not results:
        raise SystemExit(
            f"diffscore_range: 0/{tried} attempts were solvable for layout {layout} "
            f"(n_types swept: {candidates}, capacity={capacity}, timed_out={timed_out}). Raise "
            f"--samples/--time-budget, widen --n-types, or check the layout isn't pathologically hard "
            f"to fill at these type counts.")

    mn = min(results, key=lambda r: r["new_diffscore"])
    mx = max(results, key=lambda r: r["new_diffscore"])
    return {
        "layout": os.path.basename(layout_path),
        "capacity": capacity,
        "n_types_swept": candidates,
        "per_n_types": per_n_types,
        "min": mn,
        "max": mx,
        "samples_solvable": len(results),
        "samples_tried": tried,
        "timed_out": timed_out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("layout")
    ap.add_argument("--n-types", type=int, default=None)
    ap.add_argument("--samples", type=int, default=SAMPLES_DEFAULT)
    ap.add_argument("--v3-cap", type=int, default=V3_CAP_DEFAULT)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--time-budget", type=float, default=TIME_BUDGET_DEFAULT)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    t0 = time.time()
    result = diffscore_range(a.layout, n_types=a.n_types, samples=a.samples,
                              v3_cap=a.v3_cap, seed=a.seed, time_budget_s=a.time_budget)
    result["elapsed_s"] = round(time.time() - t0, 1)

    print(f"Layout: {result['layout']}  capacity={result['capacity']}  "
          f"n_types swept={result['n_types_swept']}  "
          f"({result['samples_solvable']}/{result['samples_tried']} solvable, "
          f"{result['elapsed_s']}s"
          + (", [!] TIMED OUT before sweep finished -- results may be incomplete" if result["timed_out"] else "")
          + ")")
    for nt, info in result["per_n_types"].items():
        print(f"    n_types={nt}: {info['solvable']} solvable / {info['tried']} tried"
              + ("  [!] 0 solvable -- did not contribute to min/max" if info["solvable"] == 0 else ""))
    print(f"  MIN new_diffScore: {result['min']['new_diffscore']}  [{result['min']['tier']}]  "
          f"at n_types={result['min']['n_types']}")
    print(f"  MAX new_diffScore: {result['max']['new_diffscore']}  [{result['max']['tier']}]  "
          f"at n_types={result['max']['n_types']}")

    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Saved to {a.out}")


if __name__ == "__main__":
    main()
