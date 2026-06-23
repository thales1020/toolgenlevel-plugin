"""find_bridge_L21.py — Bridge Distribution (P3 easy-top + trap-bottom) for L21-style layouts.

Bridge design (from bridge_distribution.md + SKILL §6/§17): 3-4 type groups so revealed
tiles feel FAMILIAR instead of a difficulty cliff.

| Group     | Copies | Placement                          | Role                         |
|-----------|--------|------------------------------------|------------------------------|
| Easy-only | 3x     | Top layer(s) only                  | Instant triples, disappear   |
| Bridge    | 6x     | Sparse across ALL layers (top->bot)| Player recognizes at bottom  |
| Hard-mid  | 6x     | Middle layers (hard variant only)  | Transition trap              |
| Trap-only | 3x     | Bottom layers only                 | Unfamiliar, hard             |

Three difficulty variants (bridge type count + copies-in-top-layer):

| Variant | bridge types | bridge top-copies | groups                          | ~score |
|---------|--------------|-------------------|---------------------------------|--------|
| easy    | 4            | 3 (match now)     | 5 easy + 4 bridge + 9 trap (18) | ~71    |
| harder  | 4            | 2 (need 3rd reveal)| 5 easy + 4 bridge + 9 trap (18)| ~67    |
| hard    | 2            | 1 (scattered)     | 3 easy + 2 bridge + 3 mid + 9 trap (17) | ~58 |

Critical rules enforced: bridge spans BOTH top AND bottom; top layer >=2 instant triples;
v3 solvable (definitive True per rule §15).

Usage: python find_bridge_L21.py <seed> [variant] [layout]
Example: python find_bridge_L21.py 1 easy L21
"""
import sys, os, random, json, time

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
variant = sys.argv[2] if len(sys.argv) > 2 else 'easy'
layout_id = sys.argv[3] if len(sys.argv) > 3 else 'L21'

# group spec: (n_easy, n_bridge, bridge_top, n_mid, n_trap) — must satisfy
#   n_easy*3 + n_bridge*6 + n_mid*6 + n_trap*3 == total_cells
VARIANTS = {
    'easy':   dict(n_easy=5, n_bridge=4, bridge_top=3, n_mid=0, n_trap=9),
    'harder': dict(n_easy=5, n_bridge=4, bridge_top=2, n_mid=0, n_trap=9),
    'hard':   dict(n_easy=3, n_bridge=2, bridge_top=1, n_mid=3, n_trap=9),
}
if variant not in VARIANTS:
    print(f"Unknown variant '{variant}'. Choose: {list(VARIANTS)}"); sys.exit(1)
V = VARIANTS[variant]

random.seed(seed)
weights = load_scoring_weights()
path = os.path.join(_SAMPLES, f'NewLayout_{layout_id}.json')

template = load_board_from_file(path)
all_cells_t = template.all_cells()
n = len(all_cells_t)
layer_ids = sorted({c.layer_idx for c in all_cells_t})       # ascending: [0..top]
TOP = layer_ids[-1]
total_expected = V['n_easy']*3 + V['n_bridge']*6 + V['n_mid']*6 + V['n_trap']*3
if total_expected != n:
    print(f"Variant '{variant}' sums to {total_expected} but {layout_id} has {n} cells. Adjust VARIANTS spec.")
    sys.exit(1)

# index sets per layer
layer_cells = {lid: [i for i in range(n) if all_cells_t[i].layer_idx == lid] for lid in layer_ids}


def build_bb(cells):
    m = len(cells); bb = [0]*m
    for i in range(m):
        ci = cells[i]
        for j in range(m):
            if i == j: continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx and abs(cj.x-ci.x) < 1.0 and abs(cj.y-ci.y) < 1.0:
                bb[i] |= 1 << j
    return bb

bb = build_bb(all_cells_t)
FULL = (1 << n) - 1

n_types = V['n_easy'] + V['n_bridge'] + V['n_mid'] + V['n_trap']
print(f"{layout_id} bridge[{variant}]: {n} cells, {n_types} types "
      f"({V['n_easy']} easy + {V['n_bridge']} bridge(top={V['bridge_top']}) + {V['n_mid']} mid + {V['n_trap']} trap)")


def greedy(tile_ids, runs):
    fails = 0; total = 0
    for _ in range(runs):
        active = FULL; tray = {}; cleared = 0
        while True:
            if active == 0: break
            pickable = []; a = active
            while a:
                low = a & -a; ii = low.bit_length()-1; a ^= low
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
            tray[tid] = tray.get(tid, 0)+1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0: del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1; break
        total += cleared
    return fails/runs, total/runs


def assign():
    """Return tile_ids via zone-bucketed bridge placement, or None if a zone can't fill."""
    pools = {lid: layer_cells[lid][:] for lid in layer_ids}
    for lid in pools: random.shuffle(pools[lid])
    tile_ids = [-1]*n
    tid = 0

    def draw(pref_layers, k):
        out = []
        order = pref_layers + [l for l in layer_ids if l not in pref_layers]
        for lid in order:
            while k > 0 and pools[lid]:
                out.append(pools[lid].pop()); k -= 1
            if k == 0: break
        return out

    # 1. Easy-only (3 copies) -> top layers (TOP, TOP-1)
    for _ in range(V['n_easy']):
        cells = draw([TOP, TOP-1], 3)
        if len(cells) < 3: return None
        for c in cells: tile_ids[c] = tid
        tid += 1

    # 2. Bridge (6 copies) -> bridge_top in TOP, rest spread descending (span top->bottom)
    desc = list(reversed(layer_ids[:-1]))   # [TOP-1 .. 0]
    for _ in range(V['n_bridge']):
        cells = draw([TOP], V['bridge_top'])
        remaining = 6 - len(cells)
        di = 0; guard = 0
        while remaining > 0 and guard < 500:
            lid = desc[di % len(desc)]
            if pools[lid]:
                tile_ids_cell = pools[lid].pop()
                cells.append(tile_ids_cell); remaining -= 1
            di += 1; guard += 1
        if len(cells) < 6: return None
        for c in cells: tile_ids[c] = tid
        tid += 1

    # 3. Hard-mid (6 copies) -> middle layers
    mids = layer_ids[1:-1] if len(layer_ids) > 2 else layer_ids
    for _ in range(V['n_mid']):
        cells = draw(mids, 6)
        if len(cells) < 6: return None
        for c in cells: tile_ids[c] = tid
        tid += 1

    # 4. Trap-only (3 copies) -> bottom layers
    bots = layer_ids[:2]
    for _ in range(V['n_trap']):
        cells = draw(bots, 3)
        if len(cells) < 3: return None
        for c in cells: tile_ids[c] = tid
        tid += 1

    if any(t < 0 for t in tile_ids):
        return None
    return tile_ids


best = None
t0 = time.time()
for attempt in range(100000):
    tile_ids = assign()
    if tile_ids is None:
        continue

    # gate: instant triples in top + bridge actually spans (has copy in top AND bottom)
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

    solved, _, _ = solve_v3(board, max_expansions=2_000_000, verbose=False)
    if solved is not True:
        continue

    fq, _ = greedy(tile_ids, 30)
    fail_rate, avg_clr = greedy(tile_ids, 300)

    print(f'[{attempt}] {variant} s={score:.1f} inst={instant} fail={fail_rate*100:.0f}% clr={avg_clr:.0f}/{n} ({time.time()-t0:.0f}s)', flush=True)

    quality = (instant, avg_clr, fail_rate)
    if best is None or score > best[1]:
        best = (quality, score)
        out = {
            'name': f'{layout_id} bridge_{variant} s{score:.0f}',
            'layers': [{'id': li, 'cells': [{'x': c.x, 'y': c.y, 'tile_id': c.tile_id} for c in l.cells]} for li, l in enumerate(board.layers)],
            'total_cells': board.total_cells(),
            'score': score, 'n_types': n_types, 'variant': variant,
            'instant_triples': instant, 'fail_rate': fail_rate, 'avg_cleared': avg_clr,
        }
        with open(f'bridge_{variant}_{layout_id}_candidate.json', 'w') as f:
            json.dump(out, f)
        print(f'  >> SAVED: score={score:.1f} instant={instant} fail={fail_rate*100:.0f}%', flush=True)
        # Bridge is about familiarity, not max-fail — first solvable+instant hit is good enough
        sys.exit(0)

print(f'\nDone in {time.time()-t0:.0f}s. best={best}')
