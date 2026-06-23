"""Iteratively regenerate levels until finding one that is:
  - score in [70, 90]
  - exactly 12 tile types
  - unsolvable per beam-search solver

Verification: beam search (width 10k → 50k confirmation pass).
"""
import sys, os, time, json, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

from tile_level_simulator import (
    Board, Layer, Cell, TEEngine, DifficultyScorer,
    load_board_from_file, load_scoring_weights,
)
from verify_smart_v3 import solve_v3
def beam_solve(board, beam_width, log_every=999, max_expansions=None, verbose=False):
    return solve_v3(board, max_expansions=max_expansions, verbose=verbose)

MAX_ATTEMPTS = 20000
SCORE_MIN = 50
SCORE_MAX = 70
EXACT_TYPES = 12
BEAM_FAST = 100000
BEAM_CONFIRM = 200000
FAST_EXP_CAP = 2000000
CONFIRM_EXP_CAP = 5000000

# Mixed pool: few-layer (3-4L) + medium (5-7L) layouts. Higher variety increases
# chance of hitting a late-deadlock configuration.
CANDIDATE_LAYOUTS = [
    # 3-layer
    "NewLayout_L5.json", "NewLayout_L6.json", "NewLayout_L7.json",
    "NewLayout_L8.json", "NewLayout_L10.json", "NewLayout_L33.json",
    "NewLayout_L36.json", "NewLayout_L39.json", "NewLayout_L43.json",
    "NewLayout_L49.json", "NewLayout_L60.json", "NewLayout_L82.json",
    # 4-layer
    "NewLayout_L13.json", "NewLayout_L18.json", "NewLayout_L19.json",
    "NewLayout_L28.json", "NewLayout_L30.json", "NewLayout_L42.json",
    "NewLayout_L53.json", "NewLayout_L57.json", "NewLayout_L58.json",
    "NewLayout_L61.json", "NewLayout_L65.json", "NewLayout_L69.json",
    "NewLayout_L70.json", "NewLayout_L75.json", "NewLayout_L77.json",
    "NewLayout_L86.json", "NewLayout_L87.json",
    # 5-layer
    "NewLayout_L50.json", "NewLayout_L74.json", "NewLayout_L80.json",
    # 6-7 layer
    "NewLayout_L100.json", "NewLayout_L115.json", "NewLayout_L116.json",
]

PARAM_GRID = [
    # (color_count, hard_code) combos that give exactly 12 effective types
    # Effective = cc + (+1 if hc>=2) + (+1 if hc>=3), capped at 25
    {"color_count": 12, "hard_code": 0},   # 12
    {"color_count": 12, "hard_code": 1},   # 12
    {"color_count": 11, "hard_code": 2},   # 12
    {"color_count": 10, "hard_code": 3},   # 12
]

KNOB_VARIANTS = [
    # Every variant MUST set top3_easy=True per user requirement
    {"distance": 15, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 15, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 2},
    {"distance": 12, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 2},
    {"distance": 10, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 15, "less_type": False, "top3_easy": True, "val_replace": True, "val_mode": 3},
    {"distance": 8, "less_type": True, "top3_easy": True, "val_replace": True, "val_mode": 1},
]


def configure_engine(params):
    eng = TEEngine()
    eng.validate = False  # don't auto-fix unsolvable
    for k, v in params.items():
        setattr(eng, k, v)
    if eng.color_count > 6 and eng.style_mode != 3:
        eng.style_mode = 3
        eng.extended = True
    elif eng.color_count > 5 and eng.style_mode == 0:
        eng.style_mode = 7
    return eng


def effective_types(board):
    types = set()
    for c in board.all_cells():
        if c.tile_id >= 0:
            types.add(c.tile_id)
    return len(types)


def top_n_cells(board, n=3):
    """Return number of cells in the top n layers (highest indices)."""
    layers = board.layers[-n:] if len(board.layers) >= n else board.layers
    return sum(len(l.cells) for l in layers)


def main():
    if len(sys.argv) > 1:
        random.seed(int(sys.argv[1]))
    weights = load_scoring_weights()
    print(f"Weights: {weights}")
    print(f"Target: score in [{SCORE_MIN}, {SCORE_MAX}], exact {EXACT_TYPES} types, unsolvable per beam")
    print(f"Beam widths: fast={BEAM_FAST:,}, confirm={BEAM_CONFIRM:,}")
    print(f"Max attempts: {MAX_ATTEMPTS}\n")

    start = time.time()
    attempt = 0
    best_score = 0
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
            print(f"      [load failed] {path}")
            continue

        eng = configure_engine(params)
        stats = eng.generate(board)

        et = effective_types(board)
        if et != EXACT_TYPES:
            continue

        score = DifficultyScorer.compute_full_score(board, weights=weights)
        final = score["final_score"]

        if final > best_score:
            best_score = final
            best_info = (layout_name, params, final, et)

        in_range = SCORE_MIN <= final <= SCORE_MAX
        # Pre-filter: levels with stripped>0 have easy triples => unlikely to deadlock deep
        bad_stripped = score.get("stripped", 0) > 0

        if not in_range:
            continue
        if bad_stripped:
            print(f"[{attempt:4d}] {layout_name:22s} score={final:6.2f} stripped={score['stripped']} -- skip (has easy triples)", flush=True)
            continue
        marker = "*"
        print(f"[{attempt:4d}] {layout_name:22s} cc={params['color_count']:2d} hc={params['hard_code']} score={final:6.2f} cover={score['cover100']} stripped=0 {marker}", flush=True)

        # Score in range -- fast beam with expansion cap (dead levels finish <1s)
        t0 = time.time()
        solved, depth, expansions = beam_solve(board, beam_width=BEAM_FAST, log_every=999, max_expansions=FAST_EXP_CAP, verbose=False)
        dt = time.time() - t0

        if solved is True:
            print(f"      X beam-fast solved at depth {depth} ({dt:.1f}s, {expansions:,} exp) -- discard", flush=True)
            continue
        if solved is None:
            print(f"      ~ beam-fast hit cap at {expansions:,} exp ({dt:.1f}s) -- likely solvable, discard", flush=True)
            continue

        # solved == False => exhaustive dead at fast. Require deadlock depth >= 40% of total cells
        total_cells = board.total_cells()
        min_depth = (total_cells * 2 + 4) // 5  # ceil(40%)
        if depth < min_depth:
            print(f"      - dead at depth {depth} but need >= {min_depth} (50% of {total_cells}) -- discard", flush=True)
            continue

        print(f"      ? fast-beam DEAD at depth {depth} (>= 50%={min_depth} of {total_cells}), {expansions:,} exp, {dt:.1f}s -- CONFIRM (width {BEAM_CONFIRM:,}, cap {CONFIRM_EXP_CAP:,})...", flush=True)
        t0 = time.time()
        solved2, depth2, exp2 = beam_solve(board, beam_width=BEAM_CONFIRM, log_every=999, max_expansions=CONFIRM_EXP_CAP, verbose=False)
        dt2 = time.time() - t0

        if solved2 is True:
            print(f"      X beam-confirm FOUND solution at depth {depth2} ({dt2:.1f}s) -- discard\n", flush=True)
            continue
        if solved2 is None:
            print(f"      ~ confirm hit cap ({exp2:,} exp, {dt2:.1f}s) -- inconclusive, discard\n", flush=True)
            continue
        if depth2 < min_depth:
            print(f"      - confirm dead at depth {depth2} but need >= {min_depth} -- discard\n", flush=True)
            continue

        print(f"\n{'='*60}")
        print(f"FOUND unsolvable level after {attempt} attempts, {time.time()-start:.1f}s")
        print(f"  layout     : {layout_name}")
        print(f"  params     : {params}")
        print(f"  score      : {final}")
        print(f"  types      : {et}")
        print(f"  total cells: {total_cells}  min_depth(50%)={min_depth}")
        print(f"  beam-fast  : unsolvable at depth {depth} ({dt:.1f}s)")
        print(f"  beam-conf  : unsolvable at depth {depth2} ({dt2:.1f}s)")
        print(f"  -> player can make {depth2} moves ({100*depth2/total_cells:.0f}% of board) before wall")
        print(f"{'='*60}")

        # Dump board dict
        cells_out = {}
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
                "beam_fast_width": BEAM_FAST,
                "beam_confirm_width": BEAM_CONFIRM,
                "result": "unsolvable",
            }
        }
        with open("unsolvable_candidate.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\nSaved to unsolvable_candidate.json")
        return

    print(f"\n{'='*60}")
    print(f"NO unsolvable level found in {MAX_ATTEMPTS} attempts, {time.time()-start:.1f}s")
    if best_info:
        layout, params, final, et = best_info
        print(f"Best score reached (not necessarily in range): {final:.2f}")
        print(f"  layout: {layout}, types: {et}, params: {params}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
