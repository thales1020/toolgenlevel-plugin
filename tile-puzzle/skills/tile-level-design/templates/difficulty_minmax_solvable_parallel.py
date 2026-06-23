"""Optimized sweep — SOLVABLE ONLY with parallel workers + early termination.

Optimizations:
1. v3 cap = 50k (vs 200k) — 4x faster on unsolvable
2. Reduced samples: 10 TEEngine + 10 custom (vs 20+30)
3. Multiprocessing with N_WORKERS parallel
4. Early termination: skip remaining samples if first 5 all unsolvable

Estimate: 6-15 minutes total (vs 17 hours sequential).
"""
import os, sys, csv, time, random
from multiprocessing import Pool, cpu_count
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

N_SAMPLES_ENG = 10
N_SAMPLES_CUSTOM = 10
V3_CAP = 50_000
N_WORKERS = max(4, cpu_count() - 1)
EARLY_FAIL_THRESHOLD = 5  # if first 5 samples all unsolvable, skip rest
OUTPUT = "difficulty_minmax_combined.csv"

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


def process_layout(args):
    """Process one layout: scan all tile counts, return rows for CSV."""
    li, layout_path, layout_name = args

    # Re-import inside worker (multiprocessing)
    from tile_level_simulator import TEEngine, load_board_from_file, DifficultyScorer, load_scoring_weights
    from verify_smart_v3 import solve_v3

    weights = load_scoring_weights()
    weights['D'] = 0.5

    probe = load_board_from_file(layout_path)
    if probe is None:
        return []
    total_cells = probe.total_cells()
    if total_cells % 3 != 0:
        return []
    capacity = total_cells // 3

    rows = []

    for cc in range(2, 26):
        if cc > capacity:
            continue

        bucket = {"min": None, "max": None, "n_solvable": 0, "n_total": 0}
        consecutive_fail = 0

        def update(score_dict, method):
            f = score_dict["final_score"]
            comp = (score_dict.get('layout', 0), score_dict.get('inter_group', 0),
                    score_dict.get('intra_group', 0), score_dict.get('cover100', 0),
                    score_dict.get('pickable_diversity', 0))
            if bucket["min"] is None or f < bucket["min"][0]:
                bucket["min"] = (f, method, comp)
            if bucket["max"] is None or f > bucket["max"][0]:
                bucket["max"] = (f, method, comp)

        # TEEngine samples
        for s in range(N_SAMPLES_ENG):
            if consecutive_fail >= EARLY_FAIL_THRESHOLD and bucket["n_solvable"] == 0:
                break
            random.seed(li * 10000 + cc * 100 + s)
            knob = KNOB_PRESETS[s % len(KNOB_PRESETS)]
            board = load_board_from_file(layout_path)
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
            bucket["n_total"] += 1
            solved, _, _ = solve_v3(board, max_expansions=V3_CAP, verbose=False)
            if solved is not True:
                consecutive_fail += 1
                continue
            consecutive_fail = 0
            bucket["n_solvable"] += 1
            score = DifficultyScorer.compute_full_score(board, weights=weights)
            update(score, "eng")

        # Reset for custom samples
        consecutive_fail = 0

        # Custom assignment samples
        for s in range(N_SAMPLES_CUSTOM):
            if consecutive_fail >= EARLY_FAIL_THRESHOLD and bucket["n_solvable"] == 0:
                break
            random.seed(li * 10000 + cc * 100 + 1000 + s)
            partition = random_partition_mult3(total_cells, cc)
            if partition is None:
                break
            board = load_board_from_file(layout_path)
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
            bucket["n_total"] += 1
            solved, _, _ = solve_v3(board, max_expansions=V3_CAP, verbose=False)
            if solved is not True:
                consecutive_fail += 1
                continue
            consecutive_fail = 0
            bucket["n_solvable"] += 1
            score = DifficultyScorer.compute_full_score(board, weights=weights)
            update(score, "custom")

        if bucket["n_solvable"] == 0:
            continue

        mn_score, mn_method, mn_comp = bucket["min"]
        mx_score, mx_method, mx_comp = bucket["max"]
        rows.append((
            layout_name, cc, total_cells, capacity,
            round(mn_score, 2), round(mx_score, 2),
            mn_method, mx_method,
            bucket["n_solvable"], bucket["n_total"],
            round(mn_comp[0], 2), round(mn_comp[1], 2), round(mn_comp[2], 2), mn_comp[3], mn_comp[4],
            round(mx_comp[0], 2), round(mx_comp[1], 2), round(mx_comp[2], 2), mx_comp[3], mx_comp[4],
        ))

    return rows


if __name__ == '__main__':
    sample_dir = os.path.abspath("sample_levels")
    layouts = sorted([f for f in os.listdir(sample_dir) if f.endswith(".json")])
    print(f"Layouts: {len(layouts)}, workers: {N_WORKERS}, v3_cap: {V3_CAP}")
    print(f"Samples: {N_SAMPLES_ENG} TEEngine + {N_SAMPLES_CUSTOM} custom")
    print(f"Early termination: {EARLY_FAIL_THRESHOLD} consecutive unsolvable -> skip rest")

    args_list = [(li, os.path.join(sample_dir, layout), layout)
                 for li, layout in enumerate(layouts)]

    start = time.time()
    all_rows = []
    completed = 0

    with Pool(N_WORKERS) as p:
        for rows in p.imap_unordered(process_layout, args_list):
            all_rows.extend(rows)
            completed += 1
            elapsed = time.time() - start
            print(f"[{completed}/{len(layouts)}] done ({elapsed:.0f}s, {len(all_rows)} rows so far)", flush=True)

    # Sort by layout name for consistent output
    all_rows.sort(key=lambda r: (r[0], r[1]))

    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "layout", "tile_count", "total_cells", "capacity",
            "score_min", "score_max", "method_min", "method_max",
            "n_solvable", "n_total",
            "min_layout", "min_inter", "min_intra", "min_cover100", "min_pickdiv",
            "max_layout", "max_inter", "max_intra", "max_cover100", "max_pickdiv",
        ])
        w.writerows(all_rows)

    print(f"\nSaved {len(all_rows)} rows to {OUTPUT}")
    print(f"Total time: {time.time() - start:.1f}s")
