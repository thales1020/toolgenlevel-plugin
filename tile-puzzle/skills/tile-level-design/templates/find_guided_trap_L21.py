"""Guided Trap: 3-zone cascade for L21.
Zone 1 (L4): easy types, instant triples
Zone 2 (L3,L2): easy + trap breadcrumbs (1 copy of trap type on partial cells)
Zone 3 (L1,L0): trap types in cascade chains (same type stacked vertically)

Player sees breadcrumbs during Zone 1 clear -> plans for Zone 3 -> not guessing.
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer, load_board_from_file, load_scoring_weights
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

TRAY = 7
N_PLAYOUTS = 300
SCORE_MIN, SCORE_MAX = 55, 85
FAIL_MIN = 0.80
AVG_CLEARED_MIN = 20
AVG_CLEARED_MAX = 45

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L21.json')

template = load_board_from_file(path)
all_cells = template.all_cells()
n = len(all_cells)
positions = [(c.x, c.y, c.layer_idx) for c in all_cells]

# Precompute
bb = [0] * n
bc = [0] * n
for i in range(n):
    ci = all_cells[i]
    for j in range(n):
        if i == j: continue
        cj = all_cells[j]
        if cj.layer_idx > ci.layer_idx and abs(cj.x-ci.x) < 1.0 and abs(cj.y-ci.y) < 1.0:
            bb[i] |= 1 << j
            bc[i] += 1

# Zone classification
zone1 = [i for i in range(n) if all_cells[i].layer_idx == 4]       # L4: easy
zone2 = [i for i in range(n) if all_cells[i].layer_idx in (2, 3)]  # L3,L2: transition
zone3 = [i for i in range(n) if all_cells[i].layer_idx in (0, 1)]  # L1,L0: trap

# Sort zone2 by visibility (low blockers first = more visible = better for breadcrumbs)
zone2.sort(key=lambda i: bc[i])

# Vertical stacks for cascade in zone3
stacks_z3 = {}
for i in zone3:
    c = all_cells[i]
    key = (c.x, c.y)
    if key not in stacks_z3:
        stacks_z3[key] = []
    stacks_z3[key].append(i)
for key in stacks_z3:
    stacks_z3[key].sort(key=lambda i: -all_cells[i].layer_idx)  # top first

def clone_board(tile_ids):
    board = Board()
    board.name = "L21 guided"
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

# 66 cells: 6 easy x 6 + 10 trap x 3 = 66 (16 types)
N_EASY = 6
N_TRAP = 10
EASY_TYPES = list(range(N_EASY))
TRAP_TYPES = list(range(N_EASY, N_EASY + N_TRAP))

t0 = time.time()
print(f"[seed={seed}] Guided Trap L21 | zones: {len(zone1)}/{len(zone2)}/{len(zone3)} | score {SCORE_MIN}-{SCORE_MAX}", flush=True)

for attempt in range(300000):
    tile_ids = [0] * n
    assigned = {}

    # === ZONE 1 (L4, 14 cells): Pure easy, concentrate for instant triples ===
    random.shuffle(EASY_TYPES)
    front = EASY_TYPES[:3]
    z1_pool = []
    for t in front:
        z1_pool.extend([t] * random.choice([3, 4]))
    # Fill to 14
    remaining_easy = {t: 6 for t in EASY_TYPES}
    for t in z1_pool:
        remaining_easy[t] -= 1
    while len(z1_pool) < len(zone1):
        candidates = [t for t, cnt in remaining_easy.items() if cnt > 0]
        if not candidates:
            break
        t = random.choice(candidates)
        z1_pool.append(t)
        remaining_easy[t] -= 1
    random.shuffle(z1_pool)
    if len(z1_pool) < len(zone1):
        continue
    for i, idx in enumerate(zone1):
        assigned[idx] = z1_pool[i]

    # === ZONE 2 (L3+L2, 26 cells): Easy remainder + trap BREADCRUMBS ===
    # Strategy: fill with remaining easy copies + place 1 breadcrumb per trap type
    # Breadcrumbs go on LOW blocker cells (visible sooner)
    z2_pool = []
    for t, cnt in remaining_easy.items():
        z2_pool.extend([t] * cnt)

    # Add breadcrumbs: 1 copy of each trap type (10 breadcrumbs)
    breadcrumbs = list(TRAP_TYPES)  # 1 copy each
    random.shuffle(breadcrumbs)

    # Remaining trap copies for zone3: each trap type has 3 copies, 1 goes to breadcrumb = 2 left
    trap_remaining = {t: 2 for t in TRAP_TYPES}

    z2_combined = z2_pool + breadcrumbs
    if len(z2_combined) > len(zone2):
        # Too many, reduce breadcrumbs
        excess = len(z2_combined) - len(zone2)
        breadcrumbs = breadcrumbs[:len(breadcrumbs) - excess]
        z2_combined = z2_pool + breadcrumbs
        # Restore removed breadcrumb types to zone3
        removed_types = set(TRAP_TYPES) - set(breadcrumbs)
        for t in removed_types:
            trap_remaining[t] = 3

    if len(z2_combined) < len(zone2):
        # Need more, add extra trap copies
        deficit = len(zone2) - len(z2_combined)
        extras = []
        for t in TRAP_TYPES:
            while trap_remaining[t] > 2 and len(extras) < deficit:
                extras.append(t)
                trap_remaining[t] -= 1
            if len(extras) >= deficit:
                break
        # If still not enough, add more from any trap
        while len(extras) < deficit:
            t = random.choice(TRAP_TYPES)
            if trap_remaining[t] > 1:
                extras.append(t)
                trap_remaining[t] -= 1
            elif trap_remaining[t] > 0:
                extras.append(t)
                trap_remaining[t] -= 1
            else:
                break
        z2_combined.extend(extras)

    if len(z2_combined) != len(zone2):
        continue

    # Place breadcrumbs on visible cells first (low bc), easy on rest
    # Sort: breadcrumbs first → assign to low-bc zone2 cells
    random.shuffle(z2_combined)
    # Actually, put breadcrumbs at the FRONT of pool, zone2 is sorted by bc (low first)
    bc_items = [x for x in z2_combined if x >= N_EASY]
    easy_items = [x for x in z2_combined if x < N_EASY]
    z2_ordered = bc_items + easy_items  # breadcrumbs on visible cells
    random.shuffle(bc_items)
    random.shuffle(easy_items)
    z2_ordered = bc_items + easy_items

    for i, idx in enumerate(zone2):
        assigned[idx] = z2_ordered[i]

    # === ZONE 3 (L1+L0, 26 cells): Trap types in CASCADE stacks ===
    z3_pool = []
    for t, cnt in trap_remaining.items():
        z3_pool.extend([t] * cnt)

    if len(z3_pool) != len(zone3):
        continue

    # Cascade: assign same trap type to vertical stacks
    stack_list = list(stacks_z3.values())
    random.shuffle(stack_list)
    random.shuffle(z3_pool)

    # Try to pair same types into stacks
    z3_assigned = {}
    pool_idx = 0
    for stack in stack_list:
        for cell_idx in stack:
            if pool_idx < len(z3_pool):
                z3_assigned[cell_idx] = z3_pool[pool_idx]
                pool_idx += 1

    # Better: group same types and assign to stacks
    from collections import Counter
    type_counts = Counter(z3_pool)
    type_groups = []
    for t, cnt in type_counts.items():
        type_groups.append((t, cnt))
    random.shuffle(type_groups)

    z3_cells_flat = []
    for stack in stack_list:
        z3_cells_flat.extend(stack)

    # Assign type groups sequentially to stacks (same type stays in same stack)
    z3_pool_ordered = []
    for t, cnt in type_groups:
        z3_pool_ordered.extend([t] * cnt)

    for i, cell_idx in enumerate(z3_cells_flat):
        assigned[cell_idx] = z3_pool_ordered[i]

    # Apply
    for i in range(n):
        tile_ids[i] = assigned.get(i, 0)

    # Quick checks
    nt = len(set(tile_ids))
    if nt < 14:
        continue

    # Instant triples in zone1
    pt = {}
    for i in zone1:
        t = tile_ids[i]
        pt[t] = pt.get(t, 0) + 1
    instant = sum(1 for v in pt.values() if v >= 3)
    if instant < 2:
        continue

    # Score
    board = clone_board(tile_ids)
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    final = score['final_score']
    if not (SCORE_MIN <= final <= SCORE_MAX):
        continue

    # v3
    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True:
        continue

    # Greedy
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
    if not (AVG_CLEARED_MIN <= avg_cleared <= AVG_CLEARED_MAX):
        continue

    # Double-verify
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True:
        continue

    pct = avg_cleared / n * 100
    # Count breadcrumbs in zone2
    bc_count = sum(1 for i in zone2 if tile_ids[i] >= N_EASY)
    print(f'[seed={seed} #{attempt}] FOUND! s={final:.1f} t={nt} fail={fail_rate*100:.0f}% clr={avg_cleared:.0f}/{n} ({pct:.0f}%) inst={instant} breadcrumbs={bc_count} ({time.time()-t0:.0f}s)', flush=True)

    out = {
        'name': f'L21 guided trap s{final:.0f}',
        'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
        'total_cells': n, 'score': final, 'n_types': nt,
        'fail_rate': fail_rate, 'avg_cleared': avg_cleared, 'avg_cleared_pct': pct,
        'instant_triples': instant, 'breadcrumbs_in_zone2': bc_count,
        'design': 'guided_trap: zone1=easy_cascade, zone2=easy+breadcrumbs, zone3=trap_cascade',
    }
    with open(f'guided_trap_L21_s{seed}.json', 'w') as f:
        json.dump(out, f, indent=2)
    print(f'Saved to guided_trap_L21_s{seed}.json', flush=True)
    sys.exit(0)

print(f'[seed={seed}] NO match ({time.time()-t0:.0f}s)')
