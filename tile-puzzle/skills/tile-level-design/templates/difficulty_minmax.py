"""Sweep min/max difficulty per (layout, tile_count 2-25).

Rule: if total_cells // 3 < tile_count, skip entirely (not displayed).
Only records rows where the generator actually produces exactly the requested
number of distinct tile types.
"""
import os, sys, csv, time, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import TEEngine, load_board_from_file, DifficultyScorer, load_scoring_weights

N_SAMPLES = 20
OUTPUT = "difficulty_minmax.csv"

weights = load_scoring_weights()
sample_dir = os.path.abspath("sample_levels")
layouts = sorted([f for f in os.listdir(sample_dir) if f.endswith(".json")])
print(f"Layouts: {len(layouts)}, tile counts 2-25, samples/combo: {N_SAMPLES}")
print(f"Weights: {weights}")

KNOB_PRESETS = [
    {"distance": 0,  "less_type": False, "val_replace": False, "val_mode": 0},
    {"distance": 3,  "less_type": True,  "val_replace": True,  "val_mode": 1},
    {"distance": 8,  "less_type": True,  "val_replace": True,  "val_mode": 2},
    {"distance": 15, "less_type": True,  "val_replace": True,  "val_mode": 3},
]

start = time.time()
rows = []
skipped_caps = 0
for li, layout in enumerate(layouts):
    path = os.path.join(sample_dir, layout)
    probe = load_board_from_file(path)
    if probe is None:
        continue
    total_cells = probe.total_cells()
    capacity = total_cells // 3

    buckets = {}
    for cc in range(2, 26):
        if cc > capacity:
            skipped_caps += 1
            continue
        for s in range(N_SAMPLES):
            random.seed(li * 10000 + cc * 100 + s)
            knob = KNOB_PRESETS[s % len(KNOB_PRESETS)]
            board = load_board_from_file(path)
            if board is None:
                break
            eng = TEEngine()
            eng.validate = False
            eng.color_count = cc
            eng.hard_code = (s // len(KNOB_PRESETS)) % 4
            for k, v in knob.items():
                setattr(eng, k, v)
            if cc > 6:
                eng.style_mode = 3
                eng.extended = True
            elif cc > 5:
                eng.style_mode = 7
            eng.generate(board)
            actual_types = len({c.tile_id for c in board.all_cells() if c.tile_id >= 0})
            if actual_types != cc:
                continue
            score = DifficultyScorer.compute_full_score(board, weights=weights)
            f = score["final_score"]
            if cc not in buckets:
                buckets[cc] = [f, f]
            else:
                if f < buckets[cc][0]: buckets[cc][0] = f
                if f > buckets[cc][1]: buckets[cc][1] = f

    for n_types in range(2, 26):
        if n_types in buckets:
            mn, mx = buckets[n_types]
            rows.append((layout, n_types, total_cells, capacity, round(mn, 2), round(mx, 2)))
    elapsed = time.time() - start
    print(f"[{li+1:3d}/{len(layouts)}] {layout}  cells={total_cells} cap={capacity}  buckets={sorted(buckets.keys())}  ({elapsed:.1f}s)", flush=True)

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["layout", "tile_count", "total_cells", "capacity", "score_min", "score_max"])
    w.writerows(rows)

print(f"\nSaved {len(rows)} rows to {OUTPUT}")
print(f"Skipped {skipped_caps} (layout, cc) combos where cc > capacity")
print(f"Total time: {time.time() - start:.1f}s")
