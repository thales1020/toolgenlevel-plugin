"""Use case 4: gen 1 layout from a shape with TARGET TILE COUNT + report coverage
distribution (% of tiles covered 25/50/75/100% by tiles above).

- Tile count: sweep (grid, layers) for total closest >= N, then trim down to exact N (and %3).
- Coverage: computed exactly from geometry (layout_builder.coverage_histogram).
- Verifies solvable. Reports requested-vs-achieved.

Usage:
  python fit_layout.py --icon mdi:heart --tiles 90 --out out/NewLayout_heart90.json
  python fit_layout.py --mask shape.mask.txt --tiles 120 --layers 4
"""
import sys, os, json, argparse, random, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from svg_to_mask import svg_string_to_mask
from fetch_icon import fetch_svg
from maskio import load_mask
import layout_builder as LB
from mask_to_layout import to_stones
from tile_level_simulator import Board, Layer, Cell, TEEngine
from verify_smart_v3 import solve_v3


def center(cells):
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs)+max(xs))/2*2)/2; cy = round((min(ys)+max(ys))/2*2)/2
    return [(L, round(x-cx, 2), round(y-cy, 2)) for (L, x, y) in cells]


def trim_to(cells, N):
    """Drop (len-N) cells, topmost layer + farthest-from-centre first (keeps silhouette core)."""
    cells = list(cells)
    while len(cells) > N:
        top = max(c[0] for c in cells)
        tops = [c for c in cells if c[0] == top]
        # farthest from origin first
        victim = max(tops, key=lambda c: c[1]**2 + c[2]**2)
        cells.remove(victim)
    return cells


def fit_tiles(mask_fn, target, grids, layers):
    """Find (grid,layers,cells) whose total is the smallest >= target (fallback: closest)."""
    best_over = None; best_any = None
    for g in grids:
        mask = mask_fn(g)
        for L in layers:
            cells = LB.build(mask, mode="uniform_stagger", max_layers=L)
            if len(cells) < 6:
                continue
            tot = len(cells)
            if tot >= target and (best_over is None or tot < best_over[0]):
                best_over = (tot, g, L, cells)
            if best_any is None or abs(tot - target) < abs(best_any[0] - target):
                best_any = (tot, g, L, cells)
    return best_over or best_any


def solvable_check(cells, seeds=2):
    cap = len(cells) // 3
    for s in range(seeds):
        random.seed(900 + s)
        b = Board("c"); by = {}
        for L, x, y in cells: by.setdefault(L, []).append((x, y))
        for L in sorted(by):
            ly = Layer(L)
            for (x, y) in by[L]:
                cc = Cell(x, y, L); cc.tile_id = -1; ly.cells.append(cc)
            b.layers.append(ly)
        eng = TEEngine(); eng.validate = False
        eng.color_count = max(3, min(cap, 5))
        eng.generate(b)
        if solve_v3(b, max_expansions=150000)[0] is True:
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--icon"); ap.add_argument("--mask")
    ap.add_argument("--tiles", type=int, required=True)
    ap.add_argument("--out")
    ap.add_argument("--grids", type=int, nargs="*", default=[7, 8, 9, 10, 11, 12])
    ap.add_argument("--layers", type=int, nargs="*", default=[2, 3, 4, 5])
    a = ap.parse_args()
    N = a.tiles - (a.tiles % 3)  # snap target to multiple of 3
    svg = fetch_svg(a.icon) if a.icon else None
    mask_fn = (lambda g: svg_string_to_mask(svg, grid=g)) if svg else (lambda g: load_mask(a.mask))

    tot, g, L, cells = fit_tiles(mask_fn, N, a.grids, a.layers)
    cells = [(c[0], c[1], c[2]) for c in cells]
    cells = trim_to(cells, N)
    cells = center(cells)
    cells = [list(c) for c in cells]

    hist = LB.coverage_histogram([(c[0], c[1], c[2]) for c in cells])
    total = len(cells)
    pct = {k: round(100*v/total, 1) for k, v in hist.items()}
    solv = solvable_check(cells)

    print(f"Shape={a.icon or a.mask}  target tiles={a.tiles}->{N}")
    print(f"Picked: grid={g} layers={L}  -> ACHIEVED tiles={total} (cap {total//3}) solvable={solv}")
    print("Coverage distribution (% of tiles covered X%):")
    for k in (0, 25, 50, 75, 100):
        print(f"   {k:3d}% covered: {hist[k]:3d} tiles  ({pct[k]:.0f}%)")

    if a.out:
        name = os.path.basename(a.out).replace("NewLayout_", "").replace(".json", "")
        data = to_stones(cells, name)
        data["metadata"]["coverage_pct"] = pct
        data["metadata"]["solvable"] = solv
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        print(f"SAVED {a.out}")


if __name__ == "__main__":
    main()
