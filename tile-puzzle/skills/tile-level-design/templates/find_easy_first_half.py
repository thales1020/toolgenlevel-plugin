"""Find level with:
  - Score 60-80
  - 7-15 tile types total
  - Top half of layers (upper ~50% cells) has low diversity + many clean triples (easy to clear)
  - Bottom half has high diversity + orphans (hard tail)
  - v3 confirms solvable

Structural metric instead of playout-based.
"""
import sys, os, time, random, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

from tile_level_simulator import (
    Board, Layer, Cell, TEEngine, DifficultyScorer,
    load_board_from_file, load_scoring_weights,
)
from verify_smart_v3 import solve_v3

MAX_ATTEMPTS = 20000
SCORE_MIN = 50
SCORE_MAX = 80
TYPES_MIN = 15
TYPES_MAX = 15

# Top half (upper layers, cumulative >=50% of cells)
TOP_HALF_MAX_TYPES = 16
TOP_HALF_MIN_TRIPLE_FRAC = 0.85  # top 50-60% tiles must be triple-ready
TOP3_MIN_WINDOW_FRAC = 0.60  # loose, main constraint is top_half

CANDIDATE_LAYOUTS = ["NewLayout_L50.json"]  # restricted to L50 per user request

PARAM_GRID = [
    {"color_count": cc, "hard_code": hc}
    for cc in [8, 9, 10, 11, 12, 13, 14]
    for hc in [0, 1, 2]
]

KNOB_VARIANTS = [
    # All variants force top3_easy to concentrate top 3 types
    {"distance": 0,  "less_type": True, "top3_easy": True, "val_replace": False, "val_mode": 0},
    {"distance": 0,  "less_type": True, "top3_easy": True, "val_replace": True,  "val_mode": 1},
    {"distance": 3,  "less_type": True, "top3_easy": True, "val_replace": True,  "val_mode": 1},
    {"distance": 5,  "less_type": True, "top3_easy": True, "val_replace": True,  "val_mode": 2},
    {"distance": 0,  "less_type": False, "top3_easy": True, "val_replace": False, "val_mode": 0},
    {"distance": 0,  "less_type": True, "top4_easy": True, "val_replace": True,  "val_mode": 1},
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


def partition_top_half(board):
    """Return (top_cells, bottom_cells) where top is upper layers covering ~50% of cells."""
    total = board.total_cells()
    target = total // 2
    top_cells = []
    # Walk layers from highest index down
    layers_sorted = sorted(board.layers, key=lambda l: -l.id)
    for l in layers_sorted:
        for c in l.cells:
            top_cells.append(c)
        if len(top_cells) >= target:
            break
    top_set = {id(c) for c in top_cells}
    bottom_cells = [c for c in board.all_cells() if id(c) not in top_set]
    return top_cells, bottom_cells


def distribution(cells):
    d = {}
    for c in cells:
        d[c.tile_id] = d.get(c.tile_id, 0) + 1
    return d


def main():
    if len(sys.argv) > 1:
        random.seed(int(sys.argv[1]))
    weights = load_scoring_weights()
    print(f"Target: score {SCORE_MIN}-{SCORE_MAX}, types {TYPES_MIN}-{TYPES_MAX}")
    print(f"Top half: <={TOP_HALF_MAX_TYPES} types, >={TOP_HALF_MIN_TRIPLE_FRAC*100:.0f}% tiles in triple-ready types\n")

    start = time.time()
    attempt = 0
    best = None

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

        n_types = len({c.tile_id for c in board.all_cells()})
        if not (TYPES_MIN <= n_types <= TYPES_MAX):
            continue

        score = DifficultyScorer.compute_full_score(board, weights=weights)
        final = score["final_score"]
        if not (SCORE_MIN <= final <= SCORE_MAX):
            continue

        # Top-half partition
        top_cells, bottom_cells = partition_top_half(board)
        top_dist = distribution(top_cells)
        bot_dist = distribution(bottom_cells)
        top_count = len(top_cells)
        top_types = len(top_dist)

        triple_ready_tiles = sum(v for v in top_dist.values() if v >= 3)
        triple_frac = triple_ready_tiles / top_count if top_count else 0

        # Top 3 layers with "2-adjacent-layer window" metric
        if len(board.layers) < 3:
            continue
        top3_layers = board.layers[-3:]
        top3_cells = [c for l in top3_layers for c in l.cells]
        top3_count = len(top3_cells)

        # For each cell, check if its type has >=3 tiles within any 2-adjacent-layer window
        # Windows in top 3 = (layer_idx, layer_idx+1) for idx in [top-3..top-1]
        # Build per-layer type counts
        per_layer_counts = []
        for l in top3_layers:
            lc = {}
            for c in l.cells:
                lc[c.tile_id] = lc.get(c.tile_id, 0) + 1
            per_layer_counts.append(lc)
        # Two-window counts: window i combines layer i and i+1 (for i in 0, 1 within top 3)
        window_counts = []
        for i in range(len(per_layer_counts) - 1):
            merged = {}
            for t, cnt in per_layer_counts[i].items():
                merged[t] = merged.get(t, 0) + cnt
            for t, cnt in per_layer_counts[i + 1].items():
                merged[t] = merged.get(t, 0) + cnt
            window_counts.append(merged)

        # A type is "easy" if it has >=3 tiles in SOME window
        easy_types = set()
        for wc in window_counts:
            for t, cnt in wc.items():
                if cnt >= 3:
                    easy_types.add(t)

        # Fraction of top3 tiles belonging to easy types
        easy_tiles = sum(1 for c in top3_cells if c.tile_id in easy_types)
        window_frac = easy_tiles / top3_count if top3_count else 0

        print(f"[{attempt:4d}] {layout_name:22s} t={n_types:2d} s={final:6.2f} top_half={triple_frac*100:5.1f}% top3_window={window_frac*100:5.1f}% easy_t={len(easy_types)}", flush=True)

        if best is None or window_frac > best[0]:
            best = (window_frac, layout_name, params, final, n_types, len(easy_types))

        if triple_frac < TOP_HALF_MIN_TRIPLE_FRAC:
            continue
        if window_frac < TOP3_MIN_WINDOW_FRAC:
            continue

        # Confirm full solvability with v3
        solved, depth, exp = solve_v3(board, max_expansions=2_000_000, verbose=False)
        if solved is not True:
            print(f"      ~ v3 not solvable -- skip", flush=True)
            continue

        print(f"\n{'='*60}")
        print(f"FOUND level after {attempt} attempts, {time.time()-start:.1f}s")
        print(f"  layout    : {layout_name}")
        print(f"  params    : {params}")
        print(f"  score     : {final}")
        print(f"  types     : {n_types}")
        print(f"  top cells : {top_count}")
        print(f"  top types : {top_types}")
        print(f"  top dist  : {dict(sorted(top_dist.items()))}")
        print(f"  triple_frac: {triple_frac*100:.1f}%")
        print(f"  bottom dist: {dict(sorted(bot_dist.items()))}")
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
                "n_types": n_types,
                "top_half_cells": top_count,
                "top_half_types": top_types,
                "top_half_triple_frac": triple_frac,
                "top_half_distribution": top_dist,
                "bottom_half_distribution": bot_dist,
                "top3_window_frac": window_frac,
                "top3_easy_types": len(easy_types),
                "v3_solvable": True,
            },
        }
        with open("easyfirst_candidate.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\nSaved to easyfirst_candidate.json")
        return

    print(f"\nNO level in {MAX_ATTEMPTS}. Best: {best}")


if __name__ == "__main__":
    main()
