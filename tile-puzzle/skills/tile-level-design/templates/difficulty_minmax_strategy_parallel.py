"""Strategy-aware difficulty sweep — SOLVABLE ONLY with parallel workers.

Key upgrade over difficulty_minmax_solvable_parallel.py:
- Reads layout_strategy_analysis.csv to know which strategy fits each layout
  (Random / Priority / Cascade) based on cover100 % and pickable distribution.
- Replaces blind "custom random shuffle" with strategy-aware assignment so
  the recorded min/max reflects the score range a real designer would hit
  using the right tool for that layout.
- Output adds `strategy` column = recommended strategy applied.

Strategies:
  Random   -> shuffle pool to all_cells (cover100 < 50% layouts)
  Priority -> tier1 (pickable, no overhead) get easy types first; tier3
              (cover100) get rare/trap types (50-70% cover100 layouts)
  Cascade  -> same easy type clustered into vertical stacks for waterfall
              reveals (>70% cover100 / deep uniform layouts)

Estimate: 6-15 minutes total (parallel + early termination + v3 cap 50k).
"""
import os, sys, csv, time, random
from multiprocessing import Pool, cpu_count
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

N_SAMPLES_ENG = 10
N_SAMPLES_STRATEGY = 10
V3_CAP = 50_000
N_WORKERS = max(4, cpu_count() - 1)
EARLY_FAIL_THRESHOLD = 5
OUTPUT = "difficulty_minmax_strategy.csv"
STRATEGY_CSV = "layout_strategy_analysis.csv"

KNOB_PRESETS = [
    {"distance": 0,  "less_type": False, "val_replace": False, "val_mode": 0},
    {"distance": 3,  "less_type": True,  "val_replace": True,  "val_mode": 1},
    {"distance": 8,  "less_type": True,  "val_replace": True,  "val_mode": 2},
    {"distance": 15, "less_type": True,  "val_replace": True,  "val_mode": 3},
]


def load_strategy_map():
    """Returns {layout_name -> 'Random'|'Priority'|'Cascade'} from analysis CSV."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), STRATEGY_CSV)
    if not os.path.exists(path):
        return {}
    m = {}
    with open(path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            name = row['layout']
            # CSV stores layout as e.g. "L20" or "70"; sweep iterates filenames
            # like "NewLayout_L20.json" or "NewLayout_70.json"
            m[f"NewLayout_{name}.json"] = row['recommended_strategy']
    return m


def random_partition_mult3(total, k):
    units = total // 3
    if units < k:
        return None
    parts = [1] * k
    remaining = units - k
    for _ in range(remaining):
        parts[random.randint(0, k - 1)] += 1
    return [p * 3 for p in parts]


def precompute_block_count(all_cells):
    n = len(all_cells)
    block_count = [0] * n
    for i in range(n):
        ci = all_cells[i]
        for j in range(n):
            if i == j:
                continue
            cj = all_cells[j]
            if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                block_count[i] += 1
    return block_count


def assign_random(all_cells, partition):
    """Plain random shuffle — for low cover100 layouts."""
    pool = []
    for tid, cnt in enumerate(partition):
        pool.extend([tid] * cnt)
    random.shuffle(pool)
    for i, c in enumerate(all_cells):
        c.tile_id = pool[i]


def assign_priority(all_cells, partition, block_count):
    """Easy types (high count) -> tier1 (pickable) first; rare types -> tier3 (covered)."""
    n = len(all_cells)
    # tier order: pickable first, then partial-block, then heavily covered
    order = sorted(range(n), key=lambda i: block_count[i])
    # Sort partition descending: largest type-counts get assigned to early (pickable) cells
    typed_pool = sorted(enumerate(partition), key=lambda kv: -kv[1])
    pool = []
    for tid, cnt in typed_pool:
        pool.extend([tid] * cnt)
    # Slight shuffle within tiers so we don't get a degenerate identical board each seed
    # Group cells by block_count band, shuffle within band
    bands = {}
    for idx in order:
        bands.setdefault(block_count[idx], []).append(idx)
    shuffled_order = []
    for k in sorted(bands.keys()):
        random.shuffle(bands[k])
        shuffled_order.extend(bands[k])
    for slot, cell_idx in enumerate(shuffled_order):
        all_cells[cell_idx].tile_id = pool[slot]


def assign_cascade(all_cells, partition, block_count):
    """Same easy type clustered into vertical (x,y) stacks for waterfall reveals."""
    n = len(all_cells)
    stacks = {}
    for i, c in enumerate(all_cells):
        key = (round(c.x, 1), round(c.y, 1))
        stacks.setdefault(key, []).append(i)
    # sort stacks deepest-first within each (top of stack = highest layer_idx first)
    for key in stacks:
        stacks[key].sort(key=lambda i: -all_cells[i].layer_idx)
    stack_keys = list(stacks.keys())
    random.shuffle(stack_keys)

    # Build a typed pool sorted by count desc — high-count types fill stacks first
    typed = sorted(enumerate(partition), key=lambda kv: -kv[1])
    # Flatten stacks into assignment slots in shuffled stack order
    slots = []
    for k in stack_keys:
        slots.extend(stacks[k])

    # Assign type-by-type: each type fills consecutive slots (clusters into stacks)
    pool = []
    for tid, cnt in typed:
        pool.extend([tid] * cnt)
    for slot_idx, cell_idx in enumerate(slots):
        all_cells[cell_idx].tile_id = pool[slot_idx]


def apply_strategy(strategy, all_cells, partition, block_count):
    if strategy == "Priority":
        assign_priority(all_cells, partition, block_count)
    elif strategy == "Cascade":
        assign_cascade(all_cells, partition, block_count)
    else:
        assign_random(all_cells, partition)


def process_layout(args):
    li, layout_path, layout_name, strategy = args

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

    # Precompute block_count once per layout (geometry is constant)
    block_count = precompute_block_count(probe.all_cells())

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

        # Strategy-aware samples
        consecutive_fail = 0
        for s in range(N_SAMPLES_STRATEGY):
            if consecutive_fail >= EARLY_FAIL_THRESHOLD and bucket["n_solvable"] == 0:
                break
            random.seed(li * 10000 + cc * 100 + 1000 + s)
            partition = random_partition_mult3(total_cells, cc)
            if partition is None:
                break
            board = load_board_from_file(layout_path)
            all_cells = board.all_cells()
            apply_strategy(strategy, all_cells, partition, block_count)
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
            update(score, strategy.lower())

        if bucket["n_solvable"] == 0:
            continue

        mn_score, mn_method, mn_comp = bucket["min"]
        mx_score, mx_method, mx_comp = bucket["max"]
        rows.append((
            layout_name, strategy, cc, total_cells, capacity,
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
    strategy_map = load_strategy_map()
    print(f"Layouts: {len(layouts)}, workers: {N_WORKERS}, v3_cap: {V3_CAP}")
    print(f"Samples: {N_SAMPLES_ENG} TEEngine + {N_SAMPLES_STRATEGY} strategy-aware")
    print(f"Strategy map loaded: {len(strategy_map)} layouts classified")
    print(f"Early termination: {EARLY_FAIL_THRESHOLD} consecutive unsolvable -> skip rest")

    args_list = []
    unmapped = []
    for li, layout in enumerate(layouts):
        strategy = strategy_map.get(layout, "Random")  # fallback Random if not classified
        if layout not in strategy_map:
            unmapped.append(layout)
        args_list.append((li, os.path.join(sample_dir, layout), layout, strategy))

    if unmapped:
        print(f"WARN: {len(unmapped)} layouts not in {STRATEGY_CSV} -> fallback Random: {unmapped[:5]}{'...' if len(unmapped) > 5 else ''}")

    HEADER = [
        "layout", "strategy", "tile_count", "total_cells", "capacity",
        "score_min", "score_max", "method_min", "method_max",
        "n_solvable", "n_total",
        "min_layout", "min_inter", "min_intra", "min_cover100", "min_pickdiv",
        "max_layout", "max_inter", "max_intra", "max_cover100", "max_pickdiv",
    ]

    # Resume support: skip layouts that already have rows in OUTPUT
    done_layouts = set()
    if os.path.exists(OUTPUT):
        with open(OUTPUT, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                done_layouts.add(row['layout'])
        print(f"Resuming: {len(done_layouts)} layouts already in {OUTPUT}, skipping them")
        args_list = [a for a in args_list if a[2] not in done_layouts]
    else:
        with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)

    start = time.time()
    completed = 0
    total_rows = len(done_layouts)  # rough estimate (each layout has multiple rows)

    with Pool(N_WORKERS) as p:
        for rows in p.imap_unordered(process_layout, args_list):
            # Append immediately so a crash doesn't lose progress
            if rows:
                with open(OUTPUT, "a", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)
                total_rows += len(rows)
            completed += 1
            elapsed = time.time() - start
            print(f"[{completed}/{len(args_list)}] done ({elapsed:.0f}s, ~{total_rows} rows total)", flush=True)

    print(f"\nFinal CSV: {OUTPUT}")
    print(f"Total time: {time.time() - start:.1f}s")
