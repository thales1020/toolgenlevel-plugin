"""Hybrid easy-top + trap-bottom with PRIORITY assignment v2.
Flexible: shuffle easy types but SORT by tier (pickable first, cover100 last).
This ensures easy types land on visible cells without rigid concentration.
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights, TILE_COLORS
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

TRAY = 7
N_PLAYOUTS = 300
SCORE_MIN, SCORE_MAX = 70, 85
FAIL_MIN = 0.80

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')

template = load_board_from_file(path)
all_cells_t = template.all_cells()
n = len(all_cells_t)

# Precompute blocking
bb = [0] * n
block_count = [0] * n
for i in range(n):
    ci = all_cells_t[i]
    for j in range(n):
        if i == j: continue
        cj = all_cells_t[j]
        if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
            bb[i] |= 1 << j
            block_count[i] += 1

# Classify cells
top3_ids = {l.id for l in template.layers[-3:]}
tier1 = [i for i in range(n) if all_cells_t[i].layer_idx in top3_ids and block_count[i] == 0]
tier2 = [i for i in range(n) if all_cells_t[i].layer_idx in top3_ids and 1 <= block_count[i] <= 2]
tier3 = [i for i in range(n) if all_cells_t[i].layer_idx in top3_ids and block_count[i] >= 3]
bot3 = [i for i in range(n) if all_cells_t[i].layer_idx not in top3_ids]

# Priority order: tier1 first, tier2 next, tier3 last
top_priority_order = tier1 + tier2 + tier3

print(f"L20: {n} cells | Tier1={len(tier1)} Tier2={len(tier2)} Tier3={len(tier3)} Bot={len(bot3)}")

t0 = time.time()

for attempt in range(200000):
    tile_ids = [0] * n

    # Easy pool: 6 types x 6 copies = 36
    # KEY IMPROVEMENT: sort pool so same-type tiles cluster at the START (tier1/tier2)
    # Pick 2-3 types to concentrate heavily in tier1
    easy_types = list(range(6))
    random.shuffle(easy_types)

    # Build pool: first 3 types get front-loaded (appear early in pool = land on tier1)
    front_types = easy_types[:3]  # 3 types concentrated on pickable cells
    back_types = easy_types[3:]   # 3 types spread across all tiers

    pool = []
    # Front: 3 types, each put 3-4 copies at start
    for t in front_types:
        pool.extend([t] * random.choice([3, 4]))
    # Fill rest to reach 36
    remaining = {}
    for t in range(6):
        remaining[t] = 6 - pool.count(t)
    rest = []
    for t, cnt in remaining.items():
        rest.extend([t] * cnt)
    random.shuffle(rest)
    pool.extend(rest)

    # Assign by priority order
    for i, idx in enumerate(top_priority_order):
        tile_ids[idx] = pool[i]

    # Bottom: type 6 x 6 + types 7-16 x 3 = 36
    bot_pool = [6] * 6
    for t in range(7, 17):
        bot_pool.extend([t] * 3)
    random.shuffle(bot_pool)
    for i, idx in enumerate(bot3):
        tile_ids[idx] = bot_pool[i]

    n_types = len(set(tile_ids))
    if n_types != 17:
        continue

    # Check instant triples in tier1
    pt = {}
    for i in tier1:
        t = tile_ids[i]
        pt[t] = pt.get(t, 0) + 1
    instant = sum(1 for v in pt.values() if v >= 3)
    if instant < 2:  # at least 2 visible triples
        continue

    # Score
    board = load_board_from_file(path)
    for i, c in enumerate(board.all_cells()):
        c.tile_id = tile_ids[i]
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX):
        continue

    # v3
    solved, depth, exp = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True:
        continue

    # Greedy playout
    fails = 0
    total_cleared = 0
    for run in range(N_PLAYOUTS):
        active = (1 << n) - 1
        tray = {}
        cleared = 0
        while True:
            if active == 0: break
            pickable = []
            a = active
            while a:
                low = a & -a
                ii = low.bit_length() - 1
                a ^= low
                if not (bb[ii] & active): pickable.append(ii)
            if not pickable: fails += 1; break
            if random.random() < 0.1:
                ii = random.choice(pickable)
            else:
                triple = [k for k in pickable if tray.get(tile_ids[k], 0) == 2]
                if triple: ii = random.choice(triple)
                else:
                    pair = [k for k in pickable if tray.get(tile_ids[k], 0) == 1]
                    ii = random.choice(pair) if pair else random.choice(pickable)
            tid = tile_ids[ii]
            active ^= 1 << ii
            cleared += 1
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0: del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1; break
        total_cleared += cleared
    fail_rate = fails / N_PLAYOUTS
    avg_cleared = total_cleared / N_PLAYOUTS

    if fail_rate < FAIL_MIN:
        continue

    # DOUBLE-VERIFY
    result2, picks2, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if result2 is not True:
        continue

    pct = avg_cleared / n * 100
    print(f'[{attempt}] FOUND! s={final:.1f} fail={fail_rate*100:.0f}% avg_clr={avg_cleared:.0f}/72 ({pct:.0f}%) instant={instant} ({time.time()-t0:.0f}s)', flush=True)
    print(f'  Tier1 visible: {dict(sorted(pt.items()))}')

    out = {
        'name': f'L20 hybrid priority s{final:.0f}',
        'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
        'total_cells': board.total_cells(),
        'score': final,
        'n_types': n_types,
        'fail_rate': fail_rate,
        'avg_cleared': avg_cleared,
        'avg_cleared_pct': pct,
        'instant_triples': instant,
        'tier1_distribution': pt,
    }
    with open('hybrid_priority_verified.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f'Saved to hybrid_priority_verified.json')
    break
