"""Cascade assignment for L21 (deep uniform layout).
Strategy: place same easy type in vertical stacks so picking L4 reveals
same type on L3 -> L2 -> cascade clear. Player experiences "easy waterfall"
despite deep layout.

L21: 66 cells, 5 layers (13+13+13+13+14), capacity=22
Math: 6 easy types x 6 copies + 10 trap types x 3 copies = 36+30 = 66 (with 16 types)
Or:   7 types x 6 + 8 types x 3 = 42+24 = 66 (with 15 types)
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights, TILE_COLORS
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

TRAY = 7
N_PLAYOUTS = 300
SCORE_MIN, SCORE_MAX = 60, 85
FAIL_MIN = 0.80

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L21.json')

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

tier1 = [i for i in range(n) if block_count[i] == 0]  # 14 cells, all L4

# Build vertical stacks: group cells by (x, y) position across layers
stacks = {}
for i in range(n):
    c = all_cells_t[i]
    key = (c.x, c.y)
    if key not in stacks:
        stacks[key] = []
    stacks[key].append(i)

# Sort stacks: deepest first, within stack sort by layer (top first)
for key in stacks:
    stacks[key].sort(key=lambda i: -all_cells_t[i].layer_idx)

# Build cascade chains: for each L4 cell, find the direct reveals chain
# reveals[i] = cells blocked ONLY by i (or primarily by i)
def find_cascade_chain(start_idx):
    """Find cells that form a vertical cascade from start_idx down."""
    ci = all_cells_t[start_idx]
    chain = [start_idx]
    for depth in range(4):  # max 4 layers below L4
        target_layer = ci.layer_idx - depth - 1
        if target_layer < 0:
            break
        # Find cell at similar position on target layer
        best = None
        for j in range(n):
            cj = all_cells_t[j]
            if cj.layer_idx == target_layer and abs(cj.x - ci.x) < 0.6 and abs(cj.y - ci.y) < 0.6:
                if best is None or abs(cj.x - ci.x) + abs(cj.y - ci.y) < abs(all_cells_t[best].x - ci.x) + abs(all_cells_t[best].y - ci.y):
                    best = j
        if best is not None:
            chain.append(best)
    return chain

cascade_chains = []
for i in tier1:
    chain = find_cascade_chain(i)
    if len(chain) >= 3:
        cascade_chains.append(chain)

cascade_chains.sort(key=lambda c: -len(c))
print(f"L21: {n} cells, tier1={len(tier1)}, cascade chains (>=3): {len(cascade_chains)}")
for ch in cascade_chains:
    layers = [f"L{all_cells_t[i].layer_idx}" for i in ch]
    pos = all_cells_t[ch[0]]
    print(f"  ({pos.x:+5.1f},{pos.y:+5.1f}): {' -> '.join(layers)}")

# All cell indices used in cascade chains
cascade_cells = set()
for ch in cascade_chains:
    cascade_cells.update(ch)
non_cascade = [i for i in range(n) if i not in cascade_cells]

print(f"\nCascade cells: {len(cascade_cells)}, non-cascade: {len(non_cascade)}")

# Math: 66 cells
# Option: 8 types x 6 copies + 6 types x 3 copies = 48 + 18 = 66, total 14 types
# Or: 7 types x 6 + 8 types x 3 = 42 + 24 = 66, total 15 types
# Or: 6 types x 6 + 10 types x 3 = 36 + 30 = 66, total 16 types
# Try 16 types (closer to 17 from L20 pattern)
N_EASY = 6    # types 0-5, each 6 copies = 36
N_TRAP = 10   # types 6-15, each 3 copies = 30
# Total = 36 + 30 = 66

t0 = time.time()

for attempt in range(200000):
    tile_ids = [0] * n

    easy_types = list(range(N_EASY))
    random.shuffle(easy_types)

    # CASCADE STRATEGY:
    # Assign same easy type to each cascade chain (top-to-bottom)
    # Chain of length 5: all 5 cells get same type -> cascade clear when picking from top
    # Chain of length 3: 3 cells get same type -> immediate triple cascade

    # We have ~7-12 cascade chains, assign easy types to the longest ones
    used_cascade_cells = set()
    assigned = {}  # cell_idx -> tile_id

    # Assign easy types to cascade chains
    # Each chain gets ONE easy type. If chain len >= 3, assign 3 cells same type.
    # Remaining chain cells get other easy types.
    chains_to_fill = cascade_chains[:]
    random.shuffle(chains_to_fill)

    type_pool = {}
    for t in range(N_EASY):
        type_pool[t] = 6  # 6 copies each

    for chain in chains_to_fill:
        if not type_pool:
            break
        # Pick a type with remaining copies >= min(3, chain_len)
        needed = min(3, len(chain))
        candidates = [t for t, cnt in type_pool.items() if cnt >= needed]
        if not candidates:
            continue
        t = random.choice(candidates)
        # Assign to top 'needed' cells in chain
        for ci in chain[:needed]:
            if ci not in assigned:
                assigned[ci] = t
                type_pool[t] -= 1
                used_cascade_cells.add(ci)
                if type_pool[t] <= 0:
                    del type_pool[t]
                    break

    # Fill remaining easy copies to unassigned top-layer cells (by tier priority)
    remaining_easy = []
    for t, cnt in type_pool.items():
        remaining_easy.extend([t] * cnt)
    random.shuffle(remaining_easy)

    # Priority: tier1 unassigned, then tier2-like (low block_count), then high
    unassigned_top = [i for i in range(n) if i not in assigned and all_cells_t[i].layer_idx >= 2]
    unassigned_top.sort(key=lambda i: block_count[i])

    for idx in unassigned_top:
        if not remaining_easy:
            break
        if idx not in assigned:
            assigned[idx] = remaining_easy.pop(0)

    # Fill remaining cells with trap types
    trap_pool = []
    for t in range(N_EASY, N_EASY + N_TRAP):
        trap_pool.extend([t] * 3)
    # Add any remaining easy copies
    trap_pool.extend(remaining_easy)
    random.shuffle(trap_pool)

    unassigned_all = [i for i in range(n) if i not in assigned]
    if len(trap_pool) != len(unassigned_all):
        continue  # math error, skip

    for i, idx in enumerate(unassigned_all):
        assigned[idx] = trap_pool[i]

    # Apply assignment
    for i in range(n):
        tile_ids[i] = assigned.get(i, 0)

    n_types = len(set(tile_ids))
    if n_types < 14:
        continue

    # Check instant pickable triples
    pt = {}
    for i in tier1:
        t = tile_ids[i]
        pt[t] = pt.get(t, 0) + 1
    instant = sum(1 for v in pt.values() if v >= 3)
    if instant < 2:
        continue

    # Build board
    board = load_board_from_file(path)
    for i, c in enumerate(board.all_cells()):
        c.tile_id = tile_ids[i]

    # Score
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

    # Double-verify
    result2, picks2, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if result2 is not True:
        continue

    pct = avg_cleared / n * 100
    print(f'[{attempt}] FOUND! s={final:.1f} types={n_types} fail={fail_rate*100:.0f}% avg_clr={avg_cleared:.0f}/{n} ({pct:.0f}%) instant={instant} ({time.time()-t0:.0f}s)', flush=True)
    print(f'  Tier1 visible: {dict(sorted(pt.items()))}')

    out = {
        'name': f'L21 cascade hybrid s{final:.0f}',
        'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
        'total_cells': board.total_cells(),
        'score': final,
        'n_types': n_types,
        'fail_rate': fail_rate,
        'avg_cleared': avg_cleared,
        'avg_cleared_pct': pct,
        'instant_triples': instant,
    }
    with open('cascade_L21_verified.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f'Saved to cascade_L21_verified.json')
    break
