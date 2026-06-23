"""Generate 5 levels for 5 design patterns. All optimized with:
- Precomputed blocking bitmask
- Fast clone_board (no disk reload per iteration)
- Filter order: cheap -> expensive
- Double-verify (v3 + solve_path)
- Priority/cascade assignment where applicable
"""
import sys, os, random, json, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))
from tile_level_simulator import Board, Layer, Cell, TEEngine, DifficultyScorer, load_board_from_file, load_scoring_weights, TILE_COLORS
from verify_smart_v3 import solve_v3
from solve_path import solve_with_path

TRAY = 7
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
random.seed(seed)
weights = load_scoring_weights()

# ===== SHARED UTILS =====
def precompute(path):
    template = load_board_from_file(path)
    cells = template.all_cells()
    n = len(cells)
    positions = [(c.x, c.y, c.layer_idx) for c in cells]
    bb = [0] * n
    bc = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j: continue
            ci, cj = cells[i], cells[j]
            if cj.layer_idx > ci.layer_idx and abs(cj.x-ci.x) < 1.0 and abs(cj.y-ci.y) < 1.0:
                bb[i] |= 1 << j
                bc[i] += 1
    return template, cells, n, positions, bb, bc

def clone_board(positions, tile_ids, n, name="level"):
    board = Board()
    board.name = name
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

def greedy_test(tile_ids, bb, n, n_playouts=300, quick_reject=0):
    """2-stage greedy: if quick_reject>0, run quick_reject first, reject if fail_rate < 0.5"""
    if quick_reject > 0:
        qf, _ = greedy_test(tile_ids, bb, n, quick_reject, 0)
        if qf < 0.50:
            return qf, 0
    fails = 0
    total_cleared = 0
    for _ in range(n_playouts):
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
    return fails / n_playouts, total_cleared / n_playouts

def save_result(board, score, n_types, fail_rate, avg_cleared, pattern_name, filename):
    n = board.total_cells()
    out = {
        'name': pattern_name,
        'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
        'total_cells': n, 'score': score, 'n_types': n_types,
        'fail_rate': fail_rate, 'avg_cleared': avg_cleared,
        'avg_cleared_pct': avg_cleared / n * 100,
    }
    with open(filename, 'w') as f:
        json.dump(out, f, indent=2)

def configure_engine(params):
    eng = TEEngine()
    eng.validate = False
    for k, v in params.items():
        setattr(eng, k, v)
    if eng.color_count > 6 and eng.style_mode != 3:
        eng.style_mode = 3
        eng.extended = True
    elif eng.color_count > 5 and eng.style_mode == 0:
        eng.style_mode = 7
    return eng

# ===== PRECOMPUTE FOR L20 and L21 =====
path_L20 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L20.json')
path_L21 = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'sample_layouts/NewLayout_L21.json')

t_L20, c_L20, n_L20, pos_L20, bb_L20, bc_L20 = precompute(path_L20)
t_L21, c_L21, n_L21, pos_L21, bb_L21, bc_L21 = precompute(path_L21)

tier1_L20 = [i for i in range(n_L20) if bc_L20[i] == 0]
tier1_L21 = [i for i in range(n_L21) if bc_L21[i] == 0]

# Cascade chains for L21
def find_chains(cells, n, tier1):
    chains = []
    for start in tier1:
        ci = cells[start]
        chain = [start]
        for d in range(4):
            tl = ci.layer_idx - d - 1
            if tl < 0: break
            best = None
            for j in range(n):
                cj = cells[j]
                if cj.layer_idx == tl and abs(cj.x-ci.x) < 0.6 and abs(cj.y-ci.y) < 0.6:
                    if best is None or abs(cj.x-ci.x)+abs(cj.y-ci.y) < abs(cells[best].x-ci.x)+abs(cells[best].y-ci.y):
                        best = j
            if best: chain.append(best)
        if len(chain) >= 3: chains.append(chain)
    chains.sort(key=lambda c: -len(c))
    return chains

chains_L21 = find_chains(c_L21, n_L21, tier1_L21)

KNOBS = [
    {'distance': d, 'less_type': lt, 'top3_easy': t3, 'val_replace': vr, 'val_mode': vm}
    for d in [0, 3, 5, 8, 12, 15]
    for lt in [True, False]
    for t3 in [True, False]
    for vr in [True, False]
    for vm in [0, 1, 2, 3]
]

T0 = time.time()
results = {}

# ===== PATTERN 1: Trap an (TEEngine + greedy fail >= 90%) =====
print(f"[seed={seed}] PATTERN 1: Trap an...", flush=True)
t1 = time.time()
for attempt in range(30000):
    board = load_board_from_file(path_L20)
    for c in board.all_cells(): c.tile_id = -1
    eng = configure_engine({
        'color_count': random.choice([15,16,17,18]),
        'hard_code': random.choice([0,1,2,3]),
        **random.choice(KNOBS)
    })
    eng.generate(board)
    cells = board.all_cells()
    tids = [c.tile_id for c in cells]
    nt = len(set(tids))
    if not (14 <= nt <= 20): continue
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    f = score['final_score']
    if not (70 <= f <= 90): continue
    s, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if s is not True: continue
    fr, ac = greedy_test(tids, bb_L20, n_L20, 300, quick_reject=50)
    if fr < 0.90: continue
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True: continue
    print(f"  P1 found: s={f:.1f} t={nt} fail={fr*100:.0f}% ({time.time()-t1:.1f}s)", flush=True)
    save_result(board, f, nt, fr, ac, f"P1 Trap An s{f:.0f}", f"p1_trap_{seed}.json")
    results['P1'] = (f, nt, fr, ac, time.time()-t1)
    break

# ===== PATTERN 2: Top easy + bottom hard (TEEngine + window metric) =====
print(f"[seed={seed}] PATTERN 2: Top easy...", flush=True)
t2 = time.time()
for attempt in range(30000):
    board = load_board_from_file(path_L20)
    for c in board.all_cells(): c.tile_id = -1
    eng = configure_engine({
        'color_count': random.choice([6,7,8,9,10]),
        'hard_code': random.choice([0,1]),
        'top3_easy': True, 'less_type': True, 'distance': 0,
        'val_replace': random.choice([True,False]), 'val_mode': random.choice([0,1])
    })
    eng.generate(board)
    cells_b = board.all_cells()
    tids = [c.tile_id for c in cells_b]
    nt = len(set(tids))
    if not (5 <= nt <= 12): continue
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    f = score['final_score']
    if not (30 <= f <= 60): continue
    # Window metric: top 3 layers
    top3_layers = board.layers[-3:]
    top3_cells = [c for l in top3_layers for c in l.cells]
    plc = []
    for l in top3_layers:
        lc = {}
        for c in l.cells: lc[c.tile_id] = lc.get(c.tile_id, 0) + 1
        plc.append(lc)
    easy_types = set()
    for i in range(len(plc)-1):
        merged = {}
        for t, cnt in plc[i].items(): merged[t] = merged.get(t, 0) + cnt
        for t, cnt in plc[i+1].items(): merged[t] = merged.get(t, 0) + cnt
        for t, cnt in merged.items():
            if cnt >= 3: easy_types.add(t)
    wf = sum(1 for c in top3_cells if c.tile_id in easy_types) / len(top3_cells) if top3_cells else 0
    if wf < 0.60: continue
    s, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if s is not True: continue
    print(f"  P2 found: s={f:.1f} t={nt} wf={wf*100:.0f}% ({time.time()-t2:.1f}s)", flush=True)
    fr, ac = greedy_test(tids, bb_L20, n_L20, 100)
    save_result(board, f, nt, fr, ac, f"P2 Top Easy s{f:.0f}", f"p2_topeasy_{seed}.json")
    results['P2'] = (f, nt, fr, ac, time.time()-t2)
    break

# ===== PATTERN 3: Hybrid priority (Custom + priority on L20) =====
print(f"[seed={seed}] PATTERN 3: Hybrid priority...", flush=True)
t3 = time.time()
top3_ids_L20 = {l.id for l in t_L20.layers[-3:]}
priority_order_L20 = sorted(
    [i for i in range(n_L20) if c_L20[i].layer_idx in top3_ids_L20],
    key=lambda i: bc_L20[i]
)
bot_L20 = [i for i in range(n_L20) if c_L20[i].layer_idx not in top3_ids_L20]

for attempt in range(100000):
    tile_ids = [0] * n_L20
    easy = list(range(6))
    random.shuffle(easy)
    front = easy[:3]
    pool = []
    for t in front: pool.extend([t] * random.choice([3,4]))
    rem = {}
    for t in range(6): rem[t] = 6 - pool.count(t)
    rest = []
    for t, cnt in rem.items(): rest.extend([t] * cnt)
    random.shuffle(rest)
    pool.extend(rest)
    for i, idx in enumerate(priority_order_L20): tile_ids[idx] = pool[i]
    bp = [6]*6
    for t in range(7, 17): bp.extend([t]*3)
    random.shuffle(bp)
    for i, idx in enumerate(bot_L20): tile_ids[idx] = bp[i]
    nt = len(set(tile_ids))
    if nt != 17: continue
    pt = {}
    for i in tier1_L20: pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
    if sum(1 for v in pt.values() if v >= 3) < 2: continue
    board = clone_board(pos_L20, tile_ids, n_L20, "P3")
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    f = score['final_score']
    if not (65 <= f <= 85): continue
    s, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if s is not True: continue
    fr, ac = greedy_test(tile_ids, bb_L20, n_L20)
    if fr < 0.80: continue
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True: continue
    print(f"  P3 found: s={f:.1f} t={nt} fail={fr*100:.0f}% ({time.time()-t3:.1f}s)", flush=True)
    save_result(board, f, nt, fr, ac, f"P3 Hybrid Priority s{f:.0f}", f"p3_hybrid_{seed}.json")
    results['P3'] = (f, nt, fr, ac, time.time()-t3)
    break

# ===== PATTERN 4: 90% fail (TEEngine, similar to P1 but wider) =====
print(f"[seed={seed}] PATTERN 4: 90% fail...", flush=True)
t4 = time.time()
for attempt in range(30000):
    board = load_board_from_file(path_L20)
    for c in board.all_cells(): c.tile_id = -1
    eng = configure_engine({
        'color_count': random.choice([13,14,15,16,17,18,19]),
        'hard_code': random.choice([0,1,2,3]),
        **random.choice(KNOBS)
    })
    eng.generate(board)
    cells_b = board.all_cells()
    tids = [c.tile_id for c in cells_b]
    nt = len(set(tids))
    if nt < 10: continue
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    f = score['final_score']
    if not (50 <= f <= 80): continue
    s, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if s is not True: continue
    fr, ac = greedy_test(tids, bb_L20, n_L20, 300, quick_reject=50)
    if fr < 0.90: continue
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True: continue
    print(f"  P4 found: s={f:.1f} t={nt} fail={fr*100:.0f}% ({time.time()-t4:.1f}s)", flush=True)
    save_result(board, f, nt, fr, ac, f"P4 90% Fail s{f:.0f}", f"p4_90fail_{seed}.json")
    results['P4'] = (f, nt, fr, ac, time.time()-t4)
    break

# ===== PATTERN 5: Cascade 50% clear (Custom + cascade on L21) =====
print(f"[seed={seed}] PATTERN 5: Cascade 50%...", flush=True)
t5 = time.time()
for attempt in range(200000):
    tile_ids = [0] * n_L21
    tp = {t: 6 for t in range(6)}
    assigned = {}
    eo = list(range(6)); random.shuffle(eo); front = eo[:3]
    cs = chains_L21[:]; random.shuffle(cs)
    for chain in cs:
        if not tp: break
        needed = min(3, len(chain))
        cands = [t for t in front if tp.get(t,0) >= needed]
        if not cands: cands = [t for t, cnt in tp.items() if cnt >= needed]
        if not cands: continue
        t = random.choice(cands)
        for ci in chain[:needed]:
            if ci not in assigned:
                assigned[ci] = t; tp[t] -= 1
                if tp[t] <= 0: del tp[t]; break
    rem = []
    for t, cnt in tp.items(): rem.extend([t]*cnt)
    random.shuffle(rem)
    una = sorted([i for i in range(n_L21) if i not in assigned], key=lambda i: bc_L21[i])
    for idx in una:
        if not rem: break
        assigned[idx] = rem.pop(0)
    trap = []
    for t in range(6, 16): trap.extend([t]*3)
    trap.extend(rem); random.shuffle(trap)
    una2 = [i for i in range(n_L21) if i not in assigned]
    if len(trap) != len(una2): continue
    for i, idx in enumerate(una2): assigned[idx] = trap[i]
    for i in range(n_L21): tile_ids[i] = assigned.get(i, 0)
    nt = len(set(tile_ids))
    if nt < 14: continue
    pt = {}
    for i in tier1_L21: pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
    if sum(1 for v in pt.values() if v >= 3) < 2: continue
    board = clone_board(pos_L21, tile_ids, n_L21, "P5")
    score = DifficultyScorer.compute_full_score(board, weights=weights)
    f = score['final_score']
    if not (55 <= f <= 85): continue
    s, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if s is not True: continue
    fr, ac = greedy_test(tile_ids, bb_L21, n_L21)
    if fr < 0.80 or not (26 <= ac <= 40): continue
    r2, _, _, _ = solve_with_path(board, max_expansions=2_000_000)
    if r2 is not True: continue
    pct = ac / n_L21 * 100
    print(f"  P5 found: s={f:.1f} t={nt} fail={fr*100:.0f}% clr={ac:.0f}/{n_L21} ({pct:.0f}%) ({time.time()-t5:.1f}s)", flush=True)
    save_result(board, f, nt, fr, ac, f"P5 Cascade 50% s{f:.0f}", f"p5_cascade_{seed}.json")
    results['P5'] = (f, nt, fr, ac, time.time()-t5)
    break

# ===== SUMMARY =====
total = time.time() - T0
print(f"\n{'='*60}")
print(f"[seed={seed}] ALL 5 PATTERNS in {total:.1f}s")
print(f"{'='*60}")
for k in ['P1','P2','P3','P4','P5']:
    if k in results:
        f, nt, fr, ac, t = results[k]
        print(f"  {k}: score={f:.1f} types={nt} fail={fr*100:.0f}% clr={ac:.0f} time={t:.1f}s")
    else:
        print(f"  {k}: NOT FOUND")
print(f"{'='*60}")
