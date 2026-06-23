"""Template: Player clears ~40-60% then hits trap.
Works with ANY layout. Auto-selects strategy (Priority/Cascade/Random).
Optimized: precompute bb, clone in-memory, filter order, unique output per seed.

Usage: python find_clear50_trap.py <seed> [layout] [score_min] [score_max]
  seed:      RNG seed (required, use 1 11 23 47 101 239 991 1001 for 8 workers)
  layout:    layout filename in sample_levels/ (default: NewLayout_L20.json)
  score_min: min score (default: 55)
  score_max: max score (default: 85)
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

TRAY = 7
N_PLAYOUTS = 300
FAIL_MIN = 0.80

# Parse args
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
layout_file = sys.argv[2] if len(sys.argv) > 2 else 'NewLayout_L20.json'
SCORE_MIN = float(sys.argv[3]) if len(sys.argv) > 3 else 55
SCORE_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 85

random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts', layout_file)

# ===== PRECOMPUTE ONCE =====
template = load_board_from_file(path)
if template is None:
    print(f"ERROR: cannot load {path}")
    sys.exit(1)
all_cells = template.all_cells()
n = len(all_cells)
positions = [(c.x, c.y, c.layer_idx) for c in all_cells]

bb = [0] * n
bc = [0] * n
for i in range(n):
    ci = all_cells[i]
    for j in range(n):
        if i == j: continue
        cj = all_cells[j]
        if cj.layer_idx > ci.layer_idx and abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
            bb[i] |= 1 << j
            bc[i] += 1

tier1 = [i for i in range(n) if bc[i] == 0]
n_layers = len(template.layers)

# Target: clear 40-60% = 0.4*n to 0.6*n
AVG_CLEARED_MIN = int(0.40 * n)
AVG_CLEARED_MAX = int(0.60 * n)

# ===== AUTO-SELECT STRATEGY =====
# Find cascade chains (vertical stacks >= 3 deep)
def find_chains():
    chains = []
    for start in tier1:
        ci = all_cells[start]
        chain = [start]
        for d in range(n_layers - 1):
            tl = ci.layer_idx - d - 1
            if tl < 0: break
            best = None
            for j in range(n):
                cj = all_cells[j]
                if cj.layer_idx == tl and abs(cj.x - ci.x) < 0.6 and abs(cj.y - ci.y) < 0.6:
                    if best is None or abs(cj.x-ci.x)+abs(cj.y-ci.y) < abs(all_cells[best].x-ci.x)+abs(all_cells[best].y-ci.y):
                        best = j
            if best is not None:
                chain.append(best)
        if len(chain) >= 3:
            chains.append(chain)
    chains.sort(key=lambda c: -len(c))
    return chains

chains = find_chains()

# Determine top half and bottom half
top_half_ids = set()
cumulative = 0
for l in sorted(template.layers, key=lambda l: -l.id):
    top_half_ids.add(l.id)
    cumulative += len(l.cells)
    if cumulative >= n // 2:
        break

top_indices = sorted([i for i in range(n) if all_cells[i].layer_idx in top_half_ids], key=lambda i: bc[i])
bot_indices = [i for i in range(n) if all_cells[i].layer_idx not in top_half_ids]

# Pick strategy
pickable_in_multiple_layers = len(set(all_cells[i].layer_idx for i in tier1)) > 1
has_deep_chains = len(chains) >= 3 and max(len(c) for c in chains) >= 4

if has_deep_chains and not pickable_in_multiple_layers:
    strategy = "cascade"
elif pickable_in_multiple_layers or len(tier1) > len(top_indices) * 0.3:
    strategy = "priority"
else:
    strategy = "random"

# Math: find N_EASY, N_TRAP such that N_EASY*6 + N_TRAP*3 = n
# Try N_EASY = 4,5,6,7,8
valid_configs = []
for ne in range(3, 10):
    remainder = n - ne * 6
    if remainder > 0 and remainder % 3 == 0:
        nt = remainder // 3
        if nt >= 3:
            valid_configs.append((ne, nt))

if not valid_configs:
    print(f"ERROR: no valid (easy,trap) config for {n} cells")
    sys.exit(1)

print(f"[seed={seed}] {layout_file}: {n} cells, {n_layers} layers, tier1={len(tier1)}", flush=True)
print(f"  Strategy: {strategy} | Chains: {len(chains)} | Configs: {valid_configs}", flush=True)
print(f"  Target: score {SCORE_MIN}-{SCORE_MAX}, cleared {AVG_CLEARED_MIN}-{AVG_CLEARED_MAX} ({AVG_CLEARED_MIN/n*100:.0f}-{AVG_CLEARED_MAX/n*100:.0f}%)", flush=True)

def clone_board(tile_ids):
    board = Board()
    board.name = layout_file
    layers_dict = {}
    for i in range(n):
        x, y, li = positions[i]
        if li not in layers_dict:
            layer = Layer()
            layer.id = li
            layers_dict[li] = layer
        c = Cell(x, y)
        c.tile_id = tile_ids[i]
        c.layer_idx = li
        layers_dict[li].cells.append(c)
    for li in sorted(layers_dict):
        board.layers.append(layers_dict[li])
    return board

def greedy_test(tile_ids):
    fails = 0
    total_cleared = 0
    for _ in range(N_PLAYOUTS):
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
    return fails / N_PLAYOUTS, total_cleared / N_PLAYOUTS

t0 = time.time()

for attempt in range(300000):
    N_EASY, N_TRAP = random.choice(valid_configs)
    EASY_TYPES = list(range(N_EASY))
    TRAP_TYPES = list(range(N_EASY, N_EASY + N_TRAP))

    tile_ids = [0] * n
    assigned = {}

    # === ASSIGN EASY TYPES TO TOP (strategy-dependent) ===
    if strategy == "cascade":
        # Cascade: same easy type in vertical chains
        tp = {t: 6 for t in EASY_TYPES}
        random.shuffle(EASY_TYPES)
        front = EASY_TYPES[:3]
        cs = chains[:]
        random.shuffle(cs)
        for chain in cs:
            if not tp: break
            needed = min(3, len(chain))
            cands = [t for t in front if tp.get(t, 0) >= needed]
            if not cands: cands = [t for t, cnt in tp.items() if cnt >= needed]
            if not cands: continue
            t = random.choice(cands)
            for ci in chain[:needed]:
                if ci not in assigned:
                    assigned[ci] = t
                    tp[t] -= 1
                    if tp[t] <= 0: del tp[t]; break
        rem = []
        for t, cnt in tp.items(): rem.extend([t] * cnt)
        random.shuffle(rem)
        una = sorted([i for i in top_indices if i not in assigned], key=lambda i: bc[i])
        for idx in una:
            if not rem: break
            assigned[idx] = rem.pop(0)

    elif strategy == "priority":
        # Priority: easy types on low-blocker cells first
        random.shuffle(EASY_TYPES)
        front = EASY_TYPES[:3]
        pool = []
        for t in front: pool.extend([t] * random.choice([3, 4]))
        rem_counts = {t: 6 for t in EASY_TYPES}
        for t in pool: rem_counts[t] -= 1
        while len(pool) < len(top_indices):
            cands = [t for t, cnt in rem_counts.items() if cnt > 0]
            if not cands: break
            t = random.choice(cands)
            pool.append(t)
            rem_counts[t] -= 1
        random.shuffle(pool)
        if len(pool) < len(top_indices): continue
        for i, idx in enumerate(top_indices):
            assigned[idx] = pool[i]

    else:  # random
        pool = []
        for t in EASY_TYPES: pool.extend([t] * 6)
        random.shuffle(pool)
        if len(pool) < len(top_indices): continue
        for i, idx in enumerate(top_indices):
            assigned[idx] = pool[i]

    # === ASSIGN TRAP TYPES TO BOTTOM ===
    trap_pool = []
    for t in TRAP_TYPES: trap_pool.extend([t] * 3)
    # Add any remaining easy copies
    easy_used = sum(1 for v in assigned.values())
    easy_total = N_EASY * 6
    if easy_used < easy_total:
        leftover = []
        counts = {}
        for v in assigned.values(): counts[v] = counts.get(v, 0) + 1
        for t in EASY_TYPES:
            left = 6 - counts.get(t, 0)
            leftover.extend([t] * left)
        trap_pool.extend(leftover)

    random.shuffle(trap_pool)
    unassigned = [i for i in range(n) if i not in assigned]
    if len(trap_pool) != len(unassigned): continue
    for i, idx in enumerate(unassigned):
        assigned[idx] = trap_pool[i]

    for i in range(n):
        tile_ids[i] = assigned.get(i, 0)

    # === CHEAP FILTERS ===
    nt = len(set(tile_ids))
    if nt < N_EASY + N_TRAP - 2: continue

    pt = {}
    for i in tier1: pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
    instant = sum(1 for v in pt.values() if v >= 3)
    if instant < 1: continue

    # Score
    board = clone_board(tile_ids)
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX): continue

    # v3
    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True: continue

    # Greedy
    fr, ac = greedy_test(tile_ids)
    if fr < FAIL_MIN: continue
    if not (AVG_CLEARED_MIN <= ac <= AVG_CLEARED_MAX): continue

    # Double-verify
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True: continue

    pct = ac / n * 100
    print(f'[seed={seed} #{attempt}] FOUND! s={final:.1f} t={nt} fail={fr*100:.0f}% clr={ac:.0f}/{n} ({pct:.0f}%) strat={strategy} e={N_EASY} tr={N_TRAP} inst={instant} ({time.time()-t0:.0f}s)', flush=True)

    out = {
        'name': f'{layout_file.replace(".json","")} clear50 s{final:.0f}',
        'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
        'total_cells': n, 'score': final, 'n_types': nt,
        'fail_rate': fr, 'avg_cleared': ac, 'avg_cleared_pct': pct,
        'instant_triples': instant, 'strategy': strategy,
        'layout': layout_file,
    }
    fname = f'clear50_{layout_file.replace(".json","")}_s{seed}.json'
    with open(fname, 'w') as f:
        json.dump(out, f, indent=2)
    print(f'Saved to {fname}', flush=True)
    sys.exit(0)

print(f'[seed={seed}] NO match in {attempt+1} attempts ({time.time()-t0:.0f}s)')
