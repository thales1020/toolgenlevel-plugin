"""Find a level where:
  - 12 tile types
  - score in 50-70
  - v3 confirms SOLVABLE (at least one winning path exists)
  - BUT: pure random playout fails >= 80% of the time
    (i.e., 80% of naive playthroughs deadlock)

This measures 'strategic difficulty' — level is solvable but
most move sequences lead to tray overflow.
"""
import sys, os, time, random, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

from tile_level_simulator import (
    Board, Layer, Cell, TEEngine, DifficultyScorer,
    load_board_from_file, load_scoring_weights,
)
from verify_smart_v3 import solve_v3

MAX_ATTEMPTS = 5000
SCORE_MIN = 70
SCORE_MAX = 120
EXACT_TYPES = -1  # any
N_PLAYOUTS = 500
FAIL_RATE_MIN = 0.95  # >=95% = very narrow
TRAY_SIZE = 7

CANDIDATE_LAYOUTS = [
    "NewLayout_L5.json", "NewLayout_L6.json", "NewLayout_L7.json",
    "NewLayout_L8.json", "NewLayout_L10.json", "NewLayout_L33.json",
    "NewLayout_L36.json", "NewLayout_L39.json", "NewLayout_L43.json",
    "NewLayout_L49.json", "NewLayout_L60.json", "NewLayout_L82.json",
    "NewLayout_L13.json", "NewLayout_L18.json", "NewLayout_L19.json",
    "NewLayout_L28.json", "NewLayout_L30.json", "NewLayout_L42.json",
    "NewLayout_L50.json", "NewLayout_L53.json", "NewLayout_L57.json",
    "NewLayout_L58.json", "NewLayout_L61.json", "NewLayout_L65.json",
    "NewLayout_L69.json", "NewLayout_L70.json", "NewLayout_L74.json",
    "NewLayout_L75.json", "NewLayout_L77.json", "NewLayout_L80.json",
    "NewLayout_L86.json", "NewLayout_L87.json",
    "NewLayout_L100.json", "NewLayout_L115.json", "NewLayout_L116.json",
]

PARAM_GRID = [
    {"color_count": cc, "hard_code": hc}
    for cc in [12, 14, 16, 18, 20, 22, 25]
    for hc in [0, 1, 2, 3]
]

KNOB_VARIANTS = [
    {"distance": 15, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 15, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 2},
    {"distance": 12, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 2},
    {"distance": 10, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 15, "less_type": False, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 8, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 1},
]


def configure_engine(params):
    eng = TEEngine()
    eng.validate = False
    for k, v in params.items():
        setattr(eng, k, v)
    if eng.color_count > 6 and eng.style_mode != 3:
        eng.style_mode = 3
        eng.extended = True
    elif eng.color_count > 5 and eng.style_mode == 0:
        eng.style_mode = 7
    return eng


def effective_types(board):
    return len({c.tile_id for c in board.all_cells() if c.tile_id >= 0})


def random_playout(cells, blocked_by_mask, tile_ids, n_runs):
    """Pure uniform random playout. Return fraction that fail (deadlock)."""
    n = len(cells)
    fails = 0
    for _ in range(n_runs):
        active = (1 << n) - 1
        tray = {}
        while True:
            if active == 0:
                break
            # Pickable
            pickable = []
            a = active
            while a:
                low = a & -a
                i = low.bit_length() - 1
                a ^= low
                if not (blocked_by_mask[i] & active):
                    pickable.append(i)
            if not pickable:
                fails += 1
                break
            i = random.choice(pickable)
            tid = tile_ids[i]
            active ^= 1 << i
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0:
                    del tray[tid]
            # Game over if tray reached max without any triple in it
            tsize = sum(tray.values())
            if tsize >= TRAY_SIZE and not any(v >= 3 for v in tray.values()):
                fails += 1
                break
    return fails / n_runs


def build_bitmask_blocked_by(cells):
    n = len(cells)
    bb = [0] * n
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j:
                continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx:
                if abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                    bb[i] |= 1 << j
    return bb


def main():
    if len(sys.argv) > 1:
        random.seed(int(sys.argv[1]))
    weights = load_scoring_weights()
    print(f"Weights: {weights}")
    print(f"Target: score {SCORE_MIN}-{SCORE_MAX}, {EXACT_TYPES} types, solvable, fail_rate >= {FAIL_RATE_MIN*100:.0f}%")
    print(f"Playouts per candidate: {N_PLAYOUTS}\n")

    start = time.time()
    attempt = 0
    best_fail = 0.0
    best_info = None

    for rep in range(MAX_ATTEMPTS):
        attempt += 1
        layout_name = random.choice(CANDIDATE_LAYOUTS)
        pg = random.choice(PARAM_GRID)
        knob = random.choice(KNOB_VARIANTS)
        params = {**pg, **knob}

        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_layouts", layout_name)
        board = load_board_from_file(path)
        if board is None:
            continue

        eng = configure_engine(params)
        eng.generate(board)

        et = effective_types(board)
        if EXACT_TYPES > 0 and et != EXACT_TYPES:
            continue

        score = DifficultyScorer.compute_full_score(board, weights=weights)
        final = score["final_score"]
        if not (SCORE_MIN <= final <= SCORE_MAX):
            continue

        # Pure random playout
        cells = board.all_cells()
        bb_mask = build_bitmask_blocked_by(cells)
        tile_ids = [c.tile_id for c in cells]
        fail_rate = random_playout(cells, bb_mask, tile_ids, N_PLAYOUTS)

        if fail_rate > best_fail:
            best_fail = fail_rate
            best_info = (layout_name, params, final, fail_rate)

        status = "*" if fail_rate >= FAIL_RATE_MIN else " "
        print(f"[{attempt:4d}] {layout_name:22s} cc={params['color_count']:2d} hc={params['hard_code']} score={final:6.2f} fail={fail_rate*100:5.1f}% {status}", flush=True)

        if fail_rate < FAIL_RATE_MIN:
            continue

        # Candidate! Confirm solvable with v3 before accepting
        print(f"      -> v3 solvability check...", flush=True)
        t0 = time.time()
        solved, depth, exp = solve_v3(board, max_expansions=2_000_000, verbose=False)
        dt = time.time() - t0

        if solved is not True:
            print(f"      ~ v3 says NOT solvable ({solved}, {exp:,} exp, {dt:.1f}s) -- skip, level is too hard\n", flush=True)
            continue

        print(f"\n{'='*60}")
        print(f"FOUND 80%-fail level after {attempt} attempts, {time.time()-start:.1f}s")
        print(f"  layout   : {layout_name}")
        print(f"  params   : {params}")
        print(f"  score    : {final}")
        print(f"  fail_rate: {fail_rate*100:.1f}% ({int(fail_rate*N_PLAYOUTS)}/{N_PLAYOUTS} random playouts failed)")
        print(f"  solvable : v3 confirms (solution depth {depth}, {exp:,} exp, {dt:.2f}s)")
        print(f"{'='*60}")

        out = {
            "name": board.name,
            "layers": [
                {"id": li, "cells": [{"x": c.x, "y": c.y, "tile_id": c.tile_id} for c in l.cells]}
                for li, l in enumerate(board.layers)
            ],
            "total_cells": board.total_cells(),
            "score": score,
            "params": params,
            "layout": layout_name,
            "verification": {
                "v3_solvable": True,
                "v3_solution_depth": depth,
                "random_fail_rate": fail_rate,
                "random_playouts": N_PLAYOUTS,
            },
        }
        with open("fail80_candidate.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\nSaved to fail80_candidate.json")
        return

    print(f"\nNO level found in {MAX_ATTEMPTS} attempts. Best fail_rate: {best_fail*100:.1f}%")
    if best_info:
        print(f"  best: {best_info}")


if __name__ == "__main__":
    main()
