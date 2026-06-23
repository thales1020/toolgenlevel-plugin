"""Generate a test set of N v3-solvable levels across difficulty bands — FAST and correct.

Bundled so the model RUNS this instead of improvising (BUGLOG B1-B3). It avoids the traps that
broke ad-hoc scripts:
- uses load_board_from_file (a wrong loader / bad board_idx returns None -> '.all_cells()' crash)
- reads compute_full_score(...)['final_score'] only; that dict ALSO has component scalars + a nested
  'weights' DICT -> never round the whole dict
- non-trivial color_count/distance so levels aren't all "Very Easy", and early-terminates per level

Usage:  python templates/gen_test_set.py [N=9] [out_dir]
"""
import sys, os, json, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
from tile_level_simulator import (load_board_from_file, TEEngine, DifficultyScorer,
                                   load_scoring_weights, export_board_stones_format)
from verify_smart_v3 import solve_v3

SAMPLES = os.path.join(os.path.dirname(HERE), "sample_layouts")
# spread of layouts by size/depth so the set spans easy..hard
LAYOUTS = ["NewLayout_L25.json", "NewLayout_L60.json", "NewLayout_L20.json", "NewLayout_L74.json",
           "NewLayout_L62.json", "NewLayout_L86.json", "NewLayout_L14.json", "NewLayout_L109.json",
           "NewLayout_L54.json"]
WEIGHTS = load_scoring_weights()

def band(s):
    return ("Very Easy" if s < 5 else "Easy" if s < 25 else "Normal" if s < 55 else
            "Hard" if s < 85 else "Very Hard" if s < 120 else "Extreme")

def make_one(layout, seed0):
    """Loop seeds with non-trivial knobs until v3-solvable; early-return. None if no hit."""
    path = os.path.abspath(os.path.join(SAMPLES, layout))
    for seed in range(seed0, seed0 + 25):
        random.seed(seed)
        board = load_board_from_file(path)
        if board is None:
            return None
        for c in board.all_cells():
            c.tile_id = -1
        eng = TEEngine(); eng.validate = False
        eng.color_count = random.choice([6, 8, 10, 12])
        eng.distance = random.choice([0, 3, 5])
        eng.generate(board)
        score = DifficultyScorer.compute_full_score(board, WEIGHTS)["final_score"]
        if solve_v3(board, 100_000)[0] is True:
            return board, score
    return None

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.getcwd(), "levels", "test_set")
    os.makedirs(out, exist_ok=True)
    rows = []
    for i in range(n):
        layout = LAYOUTS[i % len(LAYOUTS)]
        r = make_one(layout, seed0=1 + i * 25)
        if r is None:
            print(f"[{i+1}] {layout}: no v3-solvable hit (skip)")
            continue
        board, score = r
        data = export_board_stones_format(board)
        name = f"test_{i+1:02d}_{layout.replace('NewLayout_', '').replace('.json', '')}_s{round(score)}.json"
        json.dump(data, open(os.path.join(out, name), "w", encoding="utf-8"),
                  separators=(",", ":"), ensure_ascii=False)
        rows.append(score)
        print(f"[{i+1}] {layout:22s} score={score:6.1f} -> {band(score):10s} v3=True  {name}")
    print(f"\nPRODUCED {len(rows)}/{n} v3-solvable -> {out}")
    if rows:
        print(f"  score range {min(rows):.1f}..{max(rows):.1f}")

if __name__ == "__main__":
    main()
