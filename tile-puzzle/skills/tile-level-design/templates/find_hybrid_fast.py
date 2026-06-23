"""find_hybrid_fast.py — Custom Random strategy (P3 easy-top + trap-bottom), ANY layout.

Layout-agnostic version of find_hybrid_custom.py. Auto-computes the type partition
from the layout's cell count, then shuffles pools per half:
  - Top half of layers  -> few easy types x 6 copies (instant triples, greedy clears ~40-50%)
  - Bottom half         -> many trap types x 3 copies (greedy dies)

Partition math (requires total_cells % 3 == 0):
  n_easy = n_top_cells // 6           # 6-copy easy types fit in top half
  n_trap = (total - 6*n_easy) // 3    # 3-copy trap types for the rest
  -> 6*n_easy + 3*n_trap == total  (guaranteed since total%3==0)

Filters (per always-solvable rule): v3 solvable (definitive True) + fail_rate >= 0.70 + score in range.

Usage: python find_hybrid_fast.py <seed> <layout> [score_min] [score_max] [fail_min]
Example: python find_hybrid_fast.py 1 L20 55 85 0.70
"""
import sys, os, random, json, time

# Locate engine + sample layouts relative to this template
_HERE = os.path.dirname(os.path.abspath(__file__))
_REF = os.path.dirname(_HERE)
for _d in (os.path.join(_REF, "engine"), "c:/Users/PC1150/Downloads/GD_Test"):
    if os.path.isfile(os.path.join(_d, "tile_level_simulator.py")):
        sys.path.insert(0, _d)
        break
_SAMPLES = os.path.join(_REF, "sample_layouts")
if not os.path.isdir(_SAMPLES):
    _SAMPLES = os.path.join(_HERE, "sample_levels")

from tile_level_simulator import load_board_from_file, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3

TRAY = 7

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
layout_id = sys.argv[2] if len(sys.argv) > 2 else 'L20'
SCORE_MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 55
SCORE_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 85
FAIL_MIN = float(sys.argv[5]) if len(sys.argv) > 5 else 0.70

random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(_SAMPLES, f'NewLayout_{layout_id}.json')


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
if n % 3 != 0:
    print(f"Layout {layout_id}: {n} cells not divisible by 3 — cannot partition cleanly.")
    sys.exit(1)

# Top half of layers = "easy zone"; bottom half = "trap zone"
layer_ids = sorted({c.layer_idx for c in all_cells_t})
half = len(layer_ids) // 2
top_layer_ids = set(layer_ids[half:])       # higher index = top = pickable
top_indices = [i for i in range(n) if all_cells_t[i].layer_idx in top_layer_ids]
bot_indices = [i for i in range(n) if all_cells_t[i].layer_idx not in top_layer_ids]
n_top = len(top_indices)

# Auto partition
n_easy = max(1, n_top // 6)
n_trap = (n - 6 * n_easy) // 3
assert 6 * n_easy + 3 * n_trap == n, f"partition mismatch {6*n_easy}+{3*n_trap} != {n}"
n_types = n_easy + n_trap

bb = build_bb(all_cells_t)
FULL = (1 << n) - 1

print(f"{layout_id}: {n} cells, top={n_top} bot={len(bot_indices)} | partition: {n_easy} easy(x6) + {n_trap} trap(x3) = {n_types} types")


def greedy(tile_ids, runs):
    fails = 0; total = 0
    for _ in range(runs):
        active = FULL; tray = {}; cleared = 0
        while True:
            if active == 0: break
            pickable = []
            a = active
            while a:
                low = a & -a; ii = low.bit_length() - 1; a ^= low
                if not (bb[ii] & active): pickable.append(ii)
            if not pickable: fails += 1; break
            if random.random() < 0.1:
                ii = random.choice(pickable)
            else:
                tri = [k for k in pickable if tray.get(tile_ids[k], 0) == 2]
                if tri: ii = random.choice(tri)
                else:
                    pr = [k for k in pickable if tray.get(tile_ids[k], 0) == 1]
                    ii = random.choice(pr) if pr else random.choice(pickable)
            tid = tile_ids[ii]; active ^= 1 << ii; cleared += 1
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0: del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1; break
        total += cleared
    return fails / runs, total / runs


best = None
t0 = time.time()
for attempt in range(100000):
    tile_ids = [0] * n

    # Easy pool: types 0..n_easy-1, 6 copies each -> top cells (shuffled)
    easy_pool = []
    for t in range(n_easy):
        easy_pool.extend([t] * 6)
    # Trap pool: types n_easy..n_types-1, 3 copies each -> bottom + top overflow
    trap_pool = []
    for t in range(n_easy, n_types):
        trap_pool.extend([t] * 3)

    random.shuffle(easy_pool); random.shuffle(trap_pool)
    # Place easy in top first; overflow top cells + all bottom get trap
    top_shuf = top_indices[:]; bot_shuf = bot_indices[:]
    random.shuffle(top_shuf); random.shuffle(bot_shuf)

    pool = easy_pool + trap_pool          # easy first
    ordered = top_shuf + bot_shuf         # top cells first
    for i, idx in enumerate(ordered):
        tile_ids[idx] = pool[i]

    # Quick gate: instant pickable triples in initial state
    pickable_init = [i for i in range(n) if not (bb[i] & FULL)]
    pt = {}
    for i in pickable_init:
        pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
    instant = sum(1 for c in pt.values() if c >= 3)
    if instant < 2:
        continue

    board = load_board_from_file(path)
    for i, c in enumerate(board.all_cells()):
        c.tile_id = tile_ids[i]

    score = DifficultyScorer.compute_full_score(board, weights=weights)['final_score']
    if not (SCORE_MIN <= score <= SCORE_MAX):
        continue

    # v3 solvable — definitive True (rule §15)
    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True:
        continue

    # 2-stage greedy
    fq, _ = greedy(tile_ids, 30)
    if fq < 0.4:
        continue
    fail_rate, avg_clr = greedy(tile_ids, 300)

    print(f'[{attempt}] s={score:.1f} inst={instant} fail={fail_rate*100:.0f}% clr={avg_clr:.0f}/{n} ({time.time()-t0:.0f}s)', flush=True)

    quality = (fail_rate, avg_clr, instant)
    if best is None or quality > best[0]:
        best = (quality, score)
        out = {
            'name': f'{layout_id} hybrid_fast s{score:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': board.total_cells(),
            'score': score, 'n_types': n_types, 'instant_triples': instant,
            'fail_rate': fail_rate, 'avg_cleared': avg_clr,
        }
        with open(f'hybrid_fast_{layout_id}_candidate.json', 'w') as f:
            json.dump(out, f)
        if fail_rate >= FAIL_MIN:
            print(f'  >> SAVED (fail {fail_rate*100:.0f}% >= {FAIL_MIN*100:.0f}%): score={score:.1f} types={n_types}', flush=True)
            sys.exit(0)

print(f'\nDone in {time.time()-t0:.0f}s. best={best}')
