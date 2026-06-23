"""mask footprint -> multi-layer layout -> NewLayout_*.json (empty).

Uses layout_builder (uniform_stagger by default) which preserves the silhouette
across layers (alternating +-0.5 stagger + area support guard), instead of the
old full pyramid that eroded the shape into a mound. Output omits "i" (true empty
template); level-gen assigns tiles later.

Usage:
  python mask_to_layout.py --mask icon.mask.txt --out NewLayout_icon.json
       [--mode uniform_stagger|capped_inset|pyramid] [--layers 4]
       [--support-thresh 0.5] [--trim] [--name icon]
"""
import sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maskio import load_mask
import layout_builder as LB


def build_cells(grid, mode="uniform_stagger", max_layers=4, support_thresh=0.5,
                keep_upper=1.0, seed=0):
    # keep_upper<1 thins UPPER layers so towers vary in height (real avg tower ~4, NOT full
    # depth) -> fewer tiles + matches the real 'deep-but-easy' profile (LAYOUT_PRIORS tower_height).
    cells = LB.build(grid, mode=mode, max_layers=max_layers, support_thresh=support_thresh,
                     keep_upper=keep_upper, seed=seed)
    cells = [[L, x, y] for (L, x, y) in cells]
    n_layers = (max(c[0] for c in cells) + 1) if cells else 0
    return cells, n_layers


def thin_mask(grid, density, seed=0):
    """Keep ~`density` fraction of ON cells (h-symmetric) -> sparse-filled shape, fewer tiles.
    Real boards have base fill ~0.46 (NOT solid); thinning the silhouette region matches that."""
    import random as _r
    if density >= 1.0:
        return grid
    rng = _r.Random(seed)
    h = len(grid); w = len(grid[0])
    out = [[0] * w for _ in range(h)]
    for r in range(h):
        for c in range(w // 2 + 1):          # decide on left half, mirror -> keep h-symmetry
            if grid[r][c] and rng.random() < density:
                out[r][c] = 1; out[r][w - 1 - c] = 1 if grid[r][w - 1 - c] else out[r][w-1-c]
    return out


def center(cells):
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2
    cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    for c in cells:
        c[1] = round(c[1] - cx, 2); c[2] = round(c[2] - cy, 2)
    return cells


def trim_to_mult3(cells):
    """Drop (total%3) cells from the topmost layer, farthest from origin first."""
    rem = len(cells) % 3
    if rem == 0:
        return cells, 0
    top = max(c[0] for c in cells)
    top_cells = [c for c in cells if c[0] == top]
    top_cells.sort(key=lambda c: -(c[1]**2 + c[2]**2))  # farthest first
    drop = set(id(c) for c in top_cells[:rem])
    return [c for c in cells if id(c) not in drop], rem


def to_stones(cells, name):
    by_layer = {}
    for L, x, y in cells:
        by_layer.setdefault(L, []).append({"x": x, "y": y})
    layers = [{"index": L, "stones": by_layer[L]} for L in sorted(by_layer)]
    total = len(cells)
    return {
        "group": 1, "tiles": "", "layers": layers, "stacks": [],
        "metadata": {
            "layout": name, "source": "icon", "n_layers": len(layers),
            "total_tiles": total, "capacity": total // 3,
            "cells_per_layer": {str(L): len(by_layer[L]) for L in sorted(by_layer)},
            "divisible_by_3": total % 3 == 0,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name")
    ap.add_argument("--mode", default="uniform_stagger",
                    choices=["uniform_stagger", "capped_inset", "pyramid"])
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--support-thresh", type=float, default=0.5)
    ap.add_argument("--density", type=float, default=1.0,
                    help="keep this fraction of base ON cells (real fill ~0.46). <1 -> sparse-filled shape, fewer tiles")
    ap.add_argument("--keep-upper", type=float, default=1.0,
                    help="keep this fraction of UPPER-layer cells (real avg tower ~4, not full depth). <1 -> thinner stack, fewer tiles")
    ap.add_argument("--trim", action="store_true")
    a = ap.parse_args()
    name = a.name or os.path.basename(a.out).replace("NewLayout_", "").replace(".json", "")
    grid = load_mask(a.mask)
    grid = thin_mask(grid, a.density)
    cells, n_layers = build_cells(grid, mode=a.mode, max_layers=a.layers,
                                  support_thresh=a.support_thresh, keep_upper=a.keep_upper)
    if not cells:
        raise SystemExit("empty mask -> no cells")
    trimmed = 0
    if a.trim:
        cells, trimmed = trim_to_mult3(cells)
    cells = center(cells)
    data = to_stones(cells, name)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    md = data["metadata"]
    print(f"SAVED {a.out}")
    print(f"  layers={md['n_layers']} total={md['total_tiles']} capacity={md['capacity']} "
          f"div3={md['divisible_by_3']} trimmed={trimmed}")
    print(f"  cells/layer={md['cells_per_layer']}")


if __name__ == "__main__":
    main()
