"""Custom tile assignment: top 3 layers easy (few types, many copies) + bottom 3 trap.

L20: 72 cells, 6 layers (36 top + 36 bottom). 17 types total.
Math: 7 types x 6 copies + 10 types x 3 copies = 72.
Assignment:
  - Top 3 (36 cells): 6 types x 6 copies = 36. Few types = many triples.
  - Bottom 3 (36 cells): 1 type x 6 + 10 types x 3 = 36. Many types = trap.
Metric:
  - Greedy clears >= 20 cells in first phase (top layers easy)
  - Overall fail rate >= 0.70 (trap in bottom)
  - v3 solvable
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights
from verify_smart_v3 import solve_v3

TRAY = 7
N_PLAYOUTS = 300
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')

def build_bb(cells):
    n = len(cells)
    bb = [0] * n
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j: continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                bb[i] |= 1 << j
    return bb

template = load_board_from_file(path)
all_cells_t = template.all_cells()
n = len(all_cells_t)
top3_ids = {l.id for l in template.layers[-3:]}
top3_indices = [i for i in range(n) if all_cells_t[i].layer_idx in top3_ids]
bot3_indices = [i for i in range(n) if all_cells_t[i].layer_idx not in top3_ids]
bb = build_bb(all_cells_t)

print(f"L20: {n} cells, top3={len(top3_indices)} bot3={len(bot3_indices)}")

best = None
t0 = time.time()

for attempt in range(100000):
    tile_ids = [0] * n

    # Top 3: 6 types (0-5), each 6 copies = 36
    top_pool = []
    for t in range(6):
        top_pool.extend([t] * 6)
    random.shuffle(top_pool)
    for i, idx in enumerate(top3_indices):
        tile_ids[idx] = top_pool[i]

    # Bottom 3: type 6 x 6 + types 7-16 x 3 = 36
    bot_pool = [6] * 6
    for t in range(7, 17):
        bot_pool.extend([t] * 3)
    random.shuffle(bot_pool)
    for i, idx in enumerate(bot3_indices):
        tile_ids[idx] = bot_pool[i]

    # Build board
    board = load_board_from_file(path)
    for i, c in enumerate(board.all_cells()):
        c.tile_id = tile_ids[i]

    n_types = len({t for t in tile_ids})
    if n_types != 17:
        continue

    # Quick check: count instant pickable triples
    pickable_init = [i for i in range(n) if not (bb[i] & ((1 << n) - 1))]
    pt_count = {}
    for i in pickable_init:
        tid = tile_ids[i]
        pt_count[tid] = pt_count.get(tid, 0) + 1
    instant = sum(1 for cnt in pt_count.values() if cnt >= 3)
    if instant < 3:
        continue

    # Score check
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (60 <= final <= 85):
        continue

    # v3 solvability
    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
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

    print(f'[{attempt}] s={final:.1f} inst={instant} fail={fail_rate*100:.0f}% avg_clr={avg_cleared:.0f}/72 ({time.time()-t0:.0f}s)', flush=True)

    quality = (avg_cleared, fail_rate, instant)
    if best is None or quality > best:
        best = quality
        out = {
            'name': f'L20 hybrid custom s{final:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': board.total_cells(),
            'score': final,
            'n_types': n_types,
            'instant_triples': instant,
            'fail_rate': fail_rate,
            'avg_cleared': avg_cleared,
        }
        with open('hybrid_trap_candidate.json', 'w') as f:
            json.dump(out, f)
        print(f'  >> SAVED best: avg_clr={avg_cleared:.0f} fail={fail_rate*100:.0f}%', flush=True)

print(f'\nDone in {time.time()-t0:.0f}s. best: {best}')
