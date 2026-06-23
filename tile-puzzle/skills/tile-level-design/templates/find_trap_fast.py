"""Fast trap level search — optimized template.

Optimizations vs find_l20_17.py:
1. Board loaded ONCE, deep-copied in memory (no disk I/O per iteration)
2. Blocking bitmask bb[] pre-computed ONCE (O(n^2) saved per candidate)
3. v3 cap reduced to 100k (90% of solvable boards solve in <50k)
4. 2-phase greedy: 30 runs first, skip if fail_rate < 0.5; full 300 only on promising
5. Greedy uses pre-built bb[] directly

Usage: python find_trap_fast.py <seed> <layout> [score_min] [score_max] [n_types_min] [n_types_max]
Example: python find_trap_fast.py 1 L25 65 90 15 20

Engine + sample layouts auto-located relative to this file (reference/engine, reference/sample_layouts).
"""
import sys, os, random, json, time, copy

# Locate engine + sample layouts relative to this template (reference/templates/..)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REF = os.path.dirname(_HERE)                       # reference/
for _d in (os.path.join(_REF, "engine"), "c:/Users/PC1150/Downloads/GD_Test"):
    if os.path.isfile(os.path.join(_d, "tile_level_simulator.py")):
        sys.path.insert(0, _d)
        break
_SAMPLES = os.path.join(_REF, "sample_layouts")
if not os.path.isdir(_SAMPLES):
    _SAMPLES = os.path.join(_HERE, "sample_levels")  # legacy fallback

from tile_level_simulator import TEEngine, Board, Layer, Cell, load_board_from_file, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3

TRAY = 7

# Parse args
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
layout_id = sys.argv[2] if len(sys.argv) > 2 else 'L20'
SCORE_MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 65
SCORE_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 90
TYPES_MIN = int(sys.argv[5]) if len(sys.argv) > 5 else 15
TYPES_MAX = int(sys.argv[6]) if len(sys.argv) > 6 else 22

random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(_SAMPLES, f'NewLayout_{layout_id}.json')

# === OPTIMIZATION 1: Load board ONCE, store structure ===
template_board = load_board_from_file(path)
template_cells = template_board.all_cells()
n = len(template_cells)
cell_positions = [(c.x, c.y, c.layer_idx) for c in template_cells]

# === OPTIMIZATION 2: Pre-compute blocking bitmask ONCE ===
bb = [0] * n
for i in range(n):
    xi, yi, li = cell_positions[i]
    for j in range(n):
        if i == j: continue
        xj, yj, lj = cell_positions[j]
        if lj > li and abs(xj - xi) < 1.0 and abs(yj - yi) < 1.0:
            bb[i] |= 1 << j

def fast_deep_copy_board(template, positions):
    """Deep copy board without disk I/O."""
    b = Board(template.name)
    for layer in template.layers:
        nl = Layer(layer.id)
        for c in layer.cells:
            nc = Cell(c.x, c.y, c.layer_idx)
            nc.tile_id = -1
            nl.cells.append(nc)
        b.layers.append(nl)
    return b

def greedy_playout(tile_ids, n_runs):
    """Run greedy playouts using pre-computed bb[]."""
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
            cleared += 1
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0: del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1; break
        total_cleared += cleared
    return fails / n_runs, total_cleared / n_runs

KNOBS = [
    {'distance': d, 'less_type': lt, 'top3_easy': t3, 'val_replace': vr, 'val_mode': vm}
    for d in [0, 3, 5, 8, 12, 15]
    for lt in [True, False]
    for t3 in [True, False]
    for vr in [True, False]
    for vm in [0, 1, 2, 3]
]

t0 = time.time()
checked = 0
v3_calls = 0
greedy_calls = 0

for attempt in range(30000):
    # Fast deep copy
    board = fast_deep_copy_board(template_board, cell_positions)
    # Copy cell structure from template for generate
    for li, layer in enumerate(template_board.layers):
        for ci, c in enumerate(layer.cells):
            board.layers[li].cells[ci].tile_id = -1

    eng = TEEngine()
    eng.validate = False
    eng.color_count = random.choice(list(range(max(TYPES_MIN-2, 5), TYPES_MAX+3)))
    eng.hard_code = random.choice([0, 1, 2, 3])
    knob = random.choice(KNOBS)
    for k, v in knob.items():
        setattr(eng, k, v)
    if eng.color_count > 6:
        eng.style_mode = 3
        eng.extended = True
    elif eng.color_count > 5:
        eng.style_mode = 7
    eng.generate(board)

    all_cells = board.all_cells()
    tile_ids = [c.tile_id for c in all_cells]
    n_types = len(set(tile_ids))
    if not (TYPES_MIN <= n_types <= TYPES_MAX):
        continue
    checked += 1

    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX):
        continue

    # === OPTIMIZATION 3: v3 with reduced cap (100k instead of 2M) ===
    v3_calls += 1
    solved, depth, exp = solve_v3(board, max_expansions=100_000, verbose=False)
    if solved is not True:
        continue

    # === OPTIMIZATION 4: 2-phase greedy ===
    greedy_calls += 1
    # Phase 1: quick 30 runs
    fail_rate_quick, avg_clr = greedy_playout(tile_ids, 30)
    if fail_rate_quick < 0.5:
        continue

    # Phase 2: full 300 runs (only for promising candidates)
    fail_rate, avg_clr = greedy_playout(tile_ids, 300)

    elapsed = time.time() - t0
    print(f'[{attempt}] s={final:.1f} t={n_types} fail={fail_rate*100:.0f}% clr={avg_clr:.0f} ({elapsed:.1f}s v3={v3_calls} gr={greedy_calls})', flush=True)

    if fail_rate >= 0.90:
        out = {
            'name': f'{layout_id} trap s{final:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': board.total_cells(),
            'score': final, 'n_types': n_types, 'fail_rate': fail_rate, 'avg_cleared': avg_clr,
        }
        with open(f'trap_{layout_id}_candidate.json', 'w') as f:
            json.dump(out, f)
        print(f'\nSAVED in {elapsed:.1f}s: score={final} types={n_types} fail={fail_rate*100:.0f}%')
        print(f'Stats: {attempt} attempts, {checked} type-match, {v3_calls} v3 calls, {greedy_calls} greedy runs')
        sys.exit(0)

elapsed = time.time() - t0
print(f'\nNO match in {elapsed:.1f}s. {attempt} attempts, {v3_calls} v3, {greedy_calls} greedy')
