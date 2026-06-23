"""OPTIMIZED hybrid custom assignment. Fixes bottleneck from find_hybrid_custom.py.
Changes: precompute bb once, clone_board in-memory, 2-stage greedy (50 then 300).

Usage: python find_hybrid_custom_fast.py <seed> [score_min] [score_max]
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights
from verify_smart_v3 import solve_v3

TRAY = 7
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
SCORE_MIN = float(sys.argv[2]) if len(sys.argv) > 2 else 60
SCORE_MAX = float(sys.argv[3]) if len(sys.argv) > 3 else 85
random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')

# === PRECOMPUTE ONCE ===
template = load_board_from_file(path)
all_cells_t = template.all_cells()
n = len(all_cells_t)
positions = [(c.x, c.y, c.layer_idx) for c in all_cells_t]

bb = [0] * n
for i in range(n):
    ci = all_cells_t[i]
    for j in range(n):
        if i == j: continue
        cj = all_cells_t[j]
        if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
            bb[i] |= 1 << j

top3_ids = {l.id for l in template.layers[-3:]}
top3_indices = [i for i in range(n) if all_cells_t[i].layer_idx in top3_ids]
bot3_indices = [i for i in range(n) if all_cells_t[i].layer_idx not in top3_ids]

def clone_board(tile_ids):
    board = Board()
    board.name = "L20 hybrid"
    ld = {}
    for i in range(n):
        x, y, li = positions[i]
        if li not in ld:
            l = Layer(); l.id = li; ld[li] = l
        c = Cell(x, y); c.tile_id = tile_ids[i]; c.layer_idx = li
        ld[li].cells.append(c)
    for li in sorted(ld): board.layers.append(ld[li])
    return board

def greedy_test(tile_ids, n_runs):
    fails = 0
    total_cleared = 0
    for _ in range(n_runs):
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
            if random.random() < 0.1: ii = random.choice(pickable)
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
    return fails / n_runs, total_cleared / n_runs

print(f"[seed={seed}] L20 hybrid custom FAST | score {SCORE_MIN}-{SCORE_MAX}", flush=True)
t0 = time.time()
best = None

for attempt in range(100000):
    tile_ids = [0] * n
    top_pool = []
    for t in range(6): top_pool.extend([t] * 6)
    random.shuffle(top_pool)
    for i, idx in enumerate(top3_indices): tile_ids[idx] = top_pool[i]

    bot_pool = [6] * 6
    for t in range(7, 17): bot_pool.extend([t] * 3)
    random.shuffle(bot_pool)
    for i, idx in enumerate(bot3_indices): tile_ids[idx] = bot_pool[i]

    nt = len(set(tile_ids))
    if nt != 17: continue

    # Instant pickable triples check
    pickable_init = [i for i in range(n) if not (bb[i] & ((1 << n) - 1))]
    pt = {}
    for i in pickable_init: pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
    if sum(1 for v in pt.values() if v >= 3) < 3: continue

    # Score
    board = clone_board(tile_ids)
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX): continue

    # v3
    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True: continue

    # 2-STAGE GREEDY: quick screen first (50 runs), full only if promising
    fr1, ac1 = greedy_test(tile_ids, 50)
    if fr1 < 0.60: continue  # quick reject

    # Full greedy (300 runs)
    fr2, ac2 = greedy_test(tile_ids, 300)
    if fr2 < 0.70: continue

    print(f'[seed={seed} #{attempt}] s={final:.1f} fail={fr2*100:.0f}% clr={ac2:.0f}/{n} ({time.time()-t0:.0f}s)', flush=True)

    quality = (ac2, fr2)
    if best is None or quality > best:
        best = quality
        out = {
            'name': f'L20 hybrid fast s{final:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': n, 'score': final, 'n_types': nt,
            'fail_rate': fr2, 'avg_cleared': ac2,
        }
        with open(f'hybrid_fast_s{seed}.json', 'w') as f:
            json.dump(out, f)
        print(f'  >> SAVED ({time.time()-t0:.0f}s)', flush=True)
        if fr2 >= 0.90:
            sys.exit(0)

print(f'Done in {time.time()-t0:.0f}s')
