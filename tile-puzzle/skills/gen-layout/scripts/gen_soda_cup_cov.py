"""Re-tune soda_cup_180 to a TARGET cover100 ratio (default 0.75) at total==180, 5 layers.
cover100 = cells with >=90% area covered by higher-layer cells (engine def). High coverage
needs FEW, TALL (h=5), DENSE towers (only top layer + thin edges stay exposed), so the
footprint is compact (~37 anchors) and heights init at MAXH. Two-phase: hit 180 -> tune cover.

Usage: python gen_soda_cup_cov.py [ratio]      e.g. 0.75
"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import claude_compose as CC
from mask_to_layout import to_stones
from gen_layouts import structural_ok, layout_diff, to_board
from tile_level_simulator import DifficultyScorer as DS
from render_png import layout_to_png

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "layouts")
TARGET, MAXH = 180, 5
RATIO = float(sys.argv[1]) if len(sys.argv) > 1 else 0.75
COVTGT = round(TARGET * RATIO)

# DENSE solid body block + small straw, ~40 anchors. Heights mix 4/5 (sum=180) so interior
# height-4 towers get 100% coverage and sparse height-5 towers cap their tops -> max coverage.
body_rows = {5: range(-3, 4), 4: range(-3, 4), 3: range(-3, 4),
             2: range(-3, 4), 1: range(-3, 4)}                        # solid 7x5 block (35 cells)
body = [(x, y) for y, xs in body_rows.items() for x in xs]
straw = [(3, 6), (3, 7), (2, 7), (1, 7), (1, 8)]                      # bent straw out the top-right
straw_set = set(straw)
core = set()                                                          # no protected set; tuner free
foot, seen = [], set()
for p in body + straw:
    if p not in seen:
        seen.add(p); foot.append(p)
N = len(foot)
cx = sum(p[0] for p in foot) / N; cy = sum(p[1] for p in foot) / N
centrality = sorted(range(N), key=lambda i: (foot[i][0] - cx) ** 2 + (foot[i][1] - cy) ** 2)


def measure(h):
    spec = [[x, y, hi] for (x, y), hi in zip(foot, h)]
    cells = CC.compose(spec, mirror=False)
    board = to_board([(c[0], c[1], c[2]) for c in cells])
    cov = DS.cover100_by_area(board, [id(c) for c in board.all_cells()], threshold=0.9)
    return len(cells), max(c[0] for c in cells) + 1, cov, cells


# phase 1: start all tall (h=MAXH) -> trim/grow to total==180
h = [MAXH for _ in foot]
rr = 0
for _ in range(6000):
    t, nlay, cov, _ = measure(h)
    if t == TARGET and nlay == 5:
        break
    if t > TARGET:
        for k in range(N):
            i = (rr + k) % N
            if foot[i] not in core and h[i] > 1:
                h[i] -= 1; rr = i + 1; break
        else:
            break
    else:
        for k in range(N):
            i = (rr + k) % N
            if h[i] < MAXH:
                h[i] += 1; rr = i + 1; break
        else:
            break
t, nlay, cov, _ = measure(h)
print(f"phase1: total={t} layers={nlay} cover100={cov} ({cov/t:.3f})  target={COVTGT}")

# phase 2: total-neutral swaps to drive cover100 -> COVTGT
inc = [i for i in range(N) if foot[i] not in straw_set]
dec = [i for i in range(N) if foot[i] not in core]
for step in range(600):
    t, nlay, cov, _ = measure(h)
    if cov == COVTGT and t == TARGET and nlay == 5:
        break
    want_up = cov < COVTGT
    best = None
    for a in inc:
        if h[a] >= MAXH:
            continue
        for b in dec:
            if a == b or h[b] <= 1:
                continue
            h[a] += 1; h[b] -= 1
            t2, nlay2, cov2, _ = measure(h)
            h[a] -= 1; h[b] += 1
            if t2 != TARGET or nlay2 != 5:
                continue
            if (want_up and cov < cov2 <= COVTGT) or (not want_up and COVTGT <= cov2 < cov) or cov2 == COVTGT:
                best = (a, b); break
        if best:
            break
    if not best:
        break
    a, b = best; h[a] += 1; h[b] -= 1

t, nlay, cov, cells = measure(h)
ok = structural_ok([(c[0], c[1], c[2]) for c in cells])
d = layout_diff(cells)
data = to_stones([list(c) for c in cells], "soda_cup_180")
data["metadata"].update({"layout_difficulty": round(d, 2), "source": "claude_compose",
                         "cover100": cov, "cover100_ratio": round(cov / t, 3)})
path = os.path.join(OUT, "NewLayout_soda_cup_180.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
print(f"FINAL: total={t} layers={nlay} cover100={cov} ratio={cov/t:.3f} diff={d:.2f} ok={ok}")
print(f"   -> {path}")
layout_to_png(path, os.path.join(OUT, "NewLayout_soda_cup_180.png"), ppu=18)
