"""Combined difficulty min/max sweep with component breakdown — SOLVABLE ONLY.

For each (layout, tile_count): runs both TEEngine + Custom, but ONLY keeps boards
that pass v3 solvability check. Captures min/max final_score plus 5 component values.

Output columns:
  layout, tile_count, total_cells, capacity,
  score_min, score_max, method_min, method_max, n_solvable, n_total,
  min_layout, min_inter, min_intra, min_cover100, min_pickdiv,
  max_layout, max_inter, max_intra, max_cover100, max_pickdiv
"""
import os, sys, csv, time, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import TEEngine, load_board_from_file, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3

N_SAMPLES_ENG = 20
N_SAMPLES_CUSTOM = 30
OUTPUT = "difficulty_minmax_combined.csv"

weights = load_scoring_weights()
weights['D'] = 0.5  # pickable_diversity weight
sample_dir = os.path.abspath("sample_levels")
layouts = sorted([f for f in os.listdir(sample_dir) if f.endswith(".json")])
print(f"Layouts: {len(layouts)}, tile counts 2-25")
print(f"Samples per combo: {N_SAMPLES_ENG} TEEngine + {N_SAMPLES_CUSTOM} custom")
print(f"Weights: {weights}")

KNOB_PRESETS = [
    {"distance": 0,  "less_type": False, "val_replace": False, "val_mode": 0},
    {"distance": 3,  "less_type": True,  "val_replace": True,  "val_mode": 1},
    {"distance": 8,  "less_type": True,  "val_replace": True,  "val_mode": 2},
    {"distance": 15, "less_type": True,  "val_replace": True,  "val_mode": 3},
]


def random_partition_mult3(total, k):
    units = total // 3
    if units < k:
        return None
    parts = [1] * k
    remaining = units - k
    for _ in range(remaining):
        parts[random.randint(0, k - 1)] += 1
    return [p * 3 for p in parts]


def score_components(s):
    return (s.get('layout', 0), s.get('inter_group', 0), s.get('intra_group', 0),
            s.get('cover100', 0), s.get('pickable_diversity', 0))


start = time.time()
rows = []
skipped = 0

for li, layout in enumerate(layouts):
    path = os.path.join(sample_dir, layout)
    probe = load_board_from_file(path)
    if probe is None:
        continue
    total_cells = probe.total_cells()
    if total_cells % 3 != 0:
        continue
    capacity = total_cells // 3

    # cc -> {min: (score, method, components), max: (...), n_solvable, n_total}
    buckets = {}

    for cc in range(2, 26):
        if cc > capacity:
            skipped += 1
            continue

        n_solv_total = 0
        n_total = 0

        def update_bucket(score_dict, method):
            f = score_dict["final_score"]
            comp = score_components(score_dict)
            if cc not in buckets:
                buckets[cc] = {"min": (f, method, comp), "max": (f, method, comp),
                               "n_solvable": 0, "n_total": 0}
            else:
                if f < buckets[cc]["min"][0]:
                    buckets[cc]["min"] = (f, method, comp)
                if f > buckets[cc]["max"][0]:
                    buckets[cc]["max"] = (f, method, comp)

        def init_count():
            if cc not in buckets:
                buckets[cc] = {"min": (0, "", (0,0,0,0,0)), "max": (0, "", (0,0,0,0,0)),
                               "n_solvable": 0, "n_total": 0}

        # TEEngine samples
        for s in range(N_SAMPLES_ENG):
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
            init_count()
            buckets[cc]["n_total"] += 1
            # v3 solvability check
            solved, _, _ = solve_v3(board, max_expansions=200_000, verbose=False)
            if solved is not True:
                continue
            buckets[cc]["n_solvable"] += 1
            score = DifficultyScorer.compute_full_score(board, weights=weights)
            update_bucket(score, "eng")

        # Custom assignment samples
        for s in range(N_SAMPLES_CUSTOM):
            random.seed(li * 10000 + cc * 100 + 1000 + s)
            partition = random_partition_mult3(total_cells, cc)
            if partition is None:
                break
            board = load_board_from_file(path)
            all_cells = board.all_cells()
            pool = []
            for tid, count in enumerate(partition):
                pool.extend([tid] * count)
            random.shuffle(pool)
            for i, c in enumerate(all_cells):
                c.tile_id = pool[i]
            actual_types = len({c.tile_id for c in all_cells})
            if actual_types != cc:
                continue
            init_count()
            buckets[cc]["n_total"] += 1
            solved, _, _ = solve_v3(board, max_expansions=200_000, verbose=False)
            if solved is not True:
                continue
            buckets[cc]["n_solvable"] += 1
            score = DifficultyScorer.compute_full_score(board, weights=weights)
            update_bucket(score, "custom")

    for n_types in range(2, 26):
        if n_types not in buckets:
            continue
        b = buckets[n_types]
        if b["n_solvable"] == 0:
            continue  # skip rows where no solvable level found
        mn_score, mn_method, mn_comp = b["min"]
        mx_score, mx_method, mx_comp = b["max"]
        rows.append((
            layout, n_types, total_cells, capacity,
            round(mn_score, 2), round(mx_score, 2),
            mn_method, mx_method,
            b["n_solvable"], b["n_total"],
            round(mn_comp[0], 2), round(mn_comp[1], 2), round(mn_comp[2], 2), mn_comp[3], mn_comp[4],
            round(mx_comp[0], 2), round(mx_comp[1], 2), round(mx_comp[2], 2), mx_comp[3], mx_comp[4],
        ))

    elapsed = time.time() - start
    print(f"[{li+1:3d}/{len(layouts)}] {layout}  cells={total_cells} cap={capacity}  "
          f"buckets={sorted(buckets.keys())}  ({elapsed:.1f}s)", flush=True)

with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "layout", "tile_count", "total_cells", "capacity",
        "score_min", "score_max", "method_min", "method_max",
        "n_solvable", "n_total",
        "min_layout", "min_inter", "min_intra", "min_cover100", "min_pickdiv",
        "max_layout", "max_inter", "max_intra", "max_cover100", "max_pickdiv",
    ])
    w.writerows(rows)

print(f"\nSaved {len(rows)} rows to {OUTPUT}")
print(f"Skipped {skipped} combos where cc > capacity")
print(f"Total time: {time.time() - start:.1f}s")
