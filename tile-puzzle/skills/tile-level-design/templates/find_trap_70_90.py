"""Trap ẩn: score 70-90, v3 solvable, greedy fail >= 90%. Layout L20."""
import sys, os, random, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import TEEngine, load_board_from_file, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3

TRAY = 7
SCORE_MIN, SCORE_MAX = 70, 90
FAIL_TARGET = 0.90
N_PLAYOUTS = 300

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 1)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')

KNOBS = [
    {'distance': d, 'less_type': lt, 'top3_easy': t3, 'val_replace': vr, 'val_mode': vm}
    for d in [0, 3, 5, 8, 12, 15]
    for lt in [True, False]
    for t3 in [True, False]
    for vr in [True, False]
    for vm in [0, 1, 2, 3]
]

best = None
for attempt in range(30000):
    board = load_board_from_file(path)
    for c in board.all_cells():
        c.tile_id = -1
    eng = TEEngine()
    eng.validate = False
    eng.color_count = random.choice([13, 14, 15, 16, 17, 18, 19])
    eng.hard_code = random.choice([0, 1, 2, 3])
    knob = random.choice(KNOBS)
    for k, v in knob.items():
        setattr(eng, k, v)
    eng.style_mode = 3
    eng.extended = True
    eng.generate(board)

    n_types = len({c.tile_id for c in board.all_cells()})
    if n_types < 10:
        continue
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX):
        continue

    solved, depth, exp = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True:
        continue

    # Greedy playout fail rate
    cells = board.all_cells()
    n = len(cells)
    tile_ids = [c.tile_id for c in cells]
    bb = [0]*n
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j: continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                bb[i] |= 1 << j
    fails = 0
    for run in range(N_PLAYOUTS):
        active = (1 << n) - 1
        tray = {}
        while True:
            if active == 0: break
            pickable = []
            a = active
            while a:
                low = a & -a
                ii = low.bit_length() - 1
                a ^= low
                if not (bb[ii] & active):
                    pickable.append(ii)
            if not pickable:
                fails += 1; break
            if random.random() < 0.1:
                ii = random.choice(pickable)
            else:
                triple = [k for k in pickable if tray.get(tile_ids[k], 0) == 2]
                if triple:
                    ii = random.choice(triple)
                else:
                    pair = [k for k in pickable if tray.get(tile_ids[k], 0) == 1]
                    ii = random.choice(pair) if pair else random.choice(pickable)
            tid = tile_ids[ii]
            active ^= 1 << ii
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0: del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1; break
    fail_rate = fails / N_PLAYOUTS
    print(f'[{attempt}] score={final:.2f} types={n_types} fail={fail_rate*100:.0f}% v3_exp={exp}', flush=True)

    if best is None or fail_rate > best[0] or (fail_rate == best[0] and abs(final - 80) < abs(best[1] - 80)):
        best = (fail_rate, final, n_types)

    if fail_rate >= FAIL_TARGET:
        out = {
            'name': f'L20 Trap An s{final:.0f} fail{fail_rate*100:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': board.total_cells(),
            'score': score,
            'n_types': n_types,
            'fail_rate': fail_rate,
            'v3_depth': depth,
            'v3_expansions': exp,
            'params': {
                'color_count': eng.color_count,
                'hard_code': eng.hard_code,
                **knob,
            },
        }
        with open('trap_70_90_candidate.json', 'w') as f:
            json.dump(out, f, indent=2)
        print(f'\nSAVED: score={final:.2f} types={n_types} fail={fail_rate*100:.0f}% v3_exp={exp}')
        sys.exit(0)

print(f'\nNO match. Best: fail={best[0]*100:.0f}% score={best[1]:.2f} types={best[2]}')
