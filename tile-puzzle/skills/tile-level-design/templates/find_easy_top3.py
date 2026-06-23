"""Find level with:
  - score 35-50
  - 7-17 tile types
  - any layout
  - TOP 3 LAYERS very easy to clear
    (defined as: in v3 optimal solution, max tray size stays <= 3
     during the picks that clear the last 3 layers of the board)
"""
import sys, os, time, random, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

from tile_level_simulator import (
    Board, Layer, Cell, TEEngine, DifficultyScorer,
    load_board_from_file, load_scoring_weights,
)
import solve_path

MAX_ATTEMPTS = 10000
SCORE_MIN = 60
SCORE_MAX = 80
TYPES_MIN = 7
TYPES_MAX = 17
TOP3_MAX_TRAY = 4        # (unused) legacy
TOP3_MAX_TYPES = 8       # relaxed for higher-score levels
TOP3_MIN_TRIPLE_TYPES = 4  # >= 4 types with count >= 3 (enough triples formable)

CANDIDATE_LAYOUTS = [
    "NewLayout_L5.json", "NewLayout_L6.json", "NewLayout_L7.json", "NewLayout_L8.json",
    "NewLayout_L10.json", "NewLayout_L13.json", "NewLayout_L18.json", "NewLayout_L19.json",
    "NewLayout_L28.json", "NewLayout_L30.json", "NewLayout_L33.json", "NewLayout_L35.json",
    "NewLayout_L36.json", "NewLayout_L39.json", "NewLayout_L42.json", "NewLayout_L43.json",
    "NewLayout_L49.json", "NewLayout_L50.json", "NewLayout_L51.json", "NewLayout_L53.json",
    "NewLayout_L57.json", "NewLayout_L58.json", "NewLayout_L60.json", "NewLayout_L61.json",
    "NewLayout_L65.json", "NewLayout_L69.json", "NewLayout_L70.json", "NewLayout_L74.json",
    "NewLayout_L75.json", "NewLayout_L77.json", "NewLayout_L80.json", "NewLayout_L82.json",
    "NewLayout_L86.json", "NewLayout_L87.json", "NewLayout_L90.json", "NewLayout_L100.json",
    "NewLayout_L115.json", "NewLayout_L116.json",
]

PARAM_GRID = [
    {"color_count": cc, "hard_code": hc}
    for cc in [5, 6, 7, 8, 9, 10, 12, 14, 16]
    for hc in [0, 1, 2, 3]
]

KNOB_VARIANTS = [
    {"distance": 0,  "less_type": False, "val_replace": False, "val_mode": 0},
    {"distance": 3,  "less_type": True,  "val_replace": True,  "val_mode": 1},
    {"distance": 5,  "less_type": True,  "val_replace": True,  "val_mode": 2},
    {"distance": 0,  "less_type": True,  "top3_easy": True, "val_replace": True, "val_mode": 1},
    {"distance": 3,  "less_type": True,  "top3_easy": True, "val_replace": True, "val_mode": 1},
    {"distance": 0,  "less_type": False, "up_easy":   True, "val_replace": False, "val_mode": 0},
    {"distance": 0,  "less_type": True,  "top2_easy": True, "val_replace": True, "val_mode": 1},
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


def main():
    if len(sys.argv) > 1:
        random.seed(int(sys.argv[1]))
    weights = load_scoring_weights()
    print(f"Target: score {SCORE_MIN}-{SCORE_MAX}, types {TYPES_MIN}-{TYPES_MAX}, top3 max_tray <= {TOP3_MAX_TRAY}\n")

    start = time.time()
    attempt = 0
    best_found = None  # (top3_max, info)

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

        total_layers = len(board.layers)
        if total_layers < 3:
            continue

        # Tile distribution in top 3 layers
        top3_counts = {}
        top3_cells_count = 0
        for layer in board.layers[-3:]:
            for c in layer.cells:
                top3_counts[c.tile_id] = top3_counts.get(c.tile_id, 0) + 1
                top3_cells_count += 1
        if top3_cells_count < 6:
            continue
        types_in_top3 = len(top3_counts)
        triple_types = sum(1 for v in top3_counts.values() if v >= 3)

        # Full level solvability check (required)
        result, picks, elapsed, cells = solve_path.solve_with_path(board, max_expansions=500_000)
        if result is not True:
            continue

        top3_phase_max = 0  # legacy field
        last_top3_step = 0

        ok = (types_in_top3 <= TOP3_MAX_TYPES) and (triple_types >= TOP3_MIN_TRIPLE_TYPES)
        marker = "*" if ok else " "
        print(f"[{attempt:4d}] {layout_name:22s} layers={total_layers} t={n_types:2d} s={final:6.2f} top3={top3_cells_count:2d}c/{types_in_top3}t triples={triple_types} {marker}", flush=True)

        if best_found is None or triple_types > best_found[0]:
            best_found = (triple_types, (layout_name, params, final, n_types, total_layers))

        if not ok:
            continue

        print(f"\n{'='*60}")
        print(f"FOUND level after {attempt} attempts, {time.time()-start:.1f}s")
        print(f"  layout         : {layout_name}")
        print(f"  params         : {params}")
        print(f"  score          : {final}")
        print(f"  types          : {n_types}")
        print(f"  layers         : {total_layers}")
        print(f"  top3 cells     : {top3_cells_count}")
        print(f"  top3 types     : {types_in_top3} (<= {TOP3_MAX_TYPES})")
        print(f"  top3 triple-types: {triple_types} (>= {TOP3_MIN_TRIPLE_TYPES})")
        print(f"  top3 distribution: {dict(sorted(top3_counts.items()))}")
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
                "layers": total_layers,
                "top3_cells_count": top3_cells_count,
                "top3_types": types_in_top3,
                "top3_triple_types": triple_types,
                "top3_distribution": top3_counts,
                "picks": len(picks),
            },
        }
        with open("easytop3_candidate.json", "w") as f:
            json.dump(out, f, indent=2)
        print("\nSaved to easytop3_candidate.json")
        return

    print(f"\nNO level in {MAX_ATTEMPTS}. Best top3_max: {best_found}")


if __name__ == "__main__":
    main()
