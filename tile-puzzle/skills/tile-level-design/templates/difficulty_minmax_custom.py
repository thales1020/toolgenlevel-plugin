"""Sweep min/max difficulty using custom tile assignment (bypass TEEngine).

For each (layout, tile_count): randomly partition cells into groups of 3+,
assign tile IDs, score. Track min/max.

Rule: each type must have count divisible by 3. Skip if tile_count > capacity.
"""
import os, sys, csv, time, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import load_board_from_file, DifficultyScorer, load_scoring_weights

N_SAMPLES = 50
OUTPUT = "difficulty_minmax_custom.csv"

weights = load_scoring_weights()
sample_dir = os.path.abspath("sample_levels")
layouts = sorted([f for f in os.listdir(sample_dir) if f.endswith(".json")])
print(f"Layouts: {len(layouts)}, tile counts 2-25, samples/combo: {N_SAMPLES}")
print(f"Weights: {weights}")


def random_partition_mult3(total, k):
    """Partition total into k positive multiples of 3.
    total must be divisible by 3. Each part >= 3."""
    units = total // 3
    if units < k:
        return None
    parts = [1] * k
    remaining = units - k
    for _ in range(remaining):
        parts[random.randint(0, k - 1)] += 1
    return [p * 3 for p in parts]


start = time.time()
rows = []
for li, layout in enumerate(layouts):
    path = os.path.join(sample_dir, layout)
    probe = load_board_from_file(path)
    if probe is None:
        continue
    total_cells = probe.total_cells()
    if total_cells % 3 != 0:
        continue
    capacity = total_cells // 3

    buckets = {}
    for cc in range(2, 26):
        if cc > capacity:
            continue
        for s in range(N_SAMPLES):
            partition = random_partition_mult3(total_cells, cc)
            if partition is None:
                break

            board = load_board_from_file(path)
            all_cells = board.all_cells()
            n = len(all_cells)

            pool = []
            for tid, count in enumerate(partition):
                pool.extend([tid] * count)
            random.shuffle(pool)

            for i, c in enumerate(all_cells):
                c.tile_id = pool[i]

            actual_types = len({c.tile_id for c in all_cells})
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
print(f"Total time: {time.time() - start:.1f}s")
