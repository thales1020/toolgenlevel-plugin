"""Quality-first layout construction — replaces the shape-eroding full pyramid.

KEY FIX (verified against the 120 real layouts): real layouts do NOT erode toward
the centre. They reuse the SAME silhouette per layer with an ALTERNATING ±0.5
stagger (even layer = integer coords, odd layer = +0.5), and a cell is kept only
if enough of its area rests on the layer below (area support guard). This keeps
the shape recognizable at every layer instead of collapsing to a generic mound.

Geometry (matches engine cover rule |dx|<1 & |dy|<1):
  base cell (col,row) at layer L -> world (x,y) = (col + s, -(row + s)), s = 0.5 if L odd else 0.0
  A layer-L cell covers a lower cell by the union of 1x1 rect intersections.

Strategies:
  uniform_stagger (default): same silhouette every layer, alternating stagger, area-support erodes only the outer ring/layer.
  capped_inset: like uniform but morphologically erode the silhouette every `inset_every` layers (gentle taper for tall stacks).
  pyramid (legacy): strict 4-supporter full pyramid (kept for convex mounds).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maskio import dims, erode, pyramid_layers


def _rect_overlap(x0, y0, x1, y1):
    """Area of overlap between two 1x1 cells centred at (x0,y0) and (x1,y1)."""
    ox = max(0.0, 1.0 - abs(x0 - x1))
    oy = max(0.0, 1.0 - abs(y0 - y1))
    return ox * oy


def _mask_cells(grid):
    h, w = dims(grid)
    return [(c, r) for r in range(h) for c in range(w) if grid[r][c]]


def build(grid, mode="uniform_stagger", max_layers=4, support_thresh=0.5, inset_every=2,
          keep_upper=1.0, seed=0):
    """Return list of cells [(layer, x, y)] (world coords).

    keep_upper<1.0 randomly thins each upper layer (L>0) to that fraction — towers reach
    varied heights instead of all full-depth, so the BFS resolve stays ~linear in depth
    (matches the real 'deep-but-easy' curve ~0.9/layer). seed makes the thinning reproducible.
    """
    if mode == "pyramid":
        return _build_pyramid(grid, max_layers)
    import random as _random
    rng = _random.Random(seed)

    h, w = dims(grid)
    base = grid
    layers_cells = []          # per-layer list of (x, y)
    prev = None                # previous layer's (x,y) list
    cur_mask = [row[:] for row in grid]
    for L in range(max_layers):
        if mode == "capped_inset" and L > 0 and L % inset_every == 0:
            cur_mask = erode(cur_mask)
        s = 0.5 if (L % 2) else 0.0
        cand = [(c + s, -(r + s)) for (c, r) in _mask_cells(cur_mask)]
        if L == 0:
            kept = cand
        else:
            kept = []
            for (x, y) in cand:
                # area resting on previous layer
                support = sum(_rect_overlap(x, y, px, py) for (px, py) in prev
                              if abs(x - px) < 1.0 and abs(y - py) < 1.0)
                if support >= support_thresh:
                    kept.append((x, y))
            if keep_upper < 1.0 and kept:
                kept = [c for c in kept if rng.random() < keep_upper] or kept[:1]
        if not kept:
            break
        layers_cells.append(kept)
        prev = kept
    out = []
    for L, cells in enumerate(layers_cells):
        for (x, y) in cells:
            out.append((L, round(x, 2), round(y, 2)))
    return out


def _build_pyramid(grid, max_layers):
    """Legacy strict pyramid (cell exists iff 4 supporters below)."""
    base = set(_mask_cells(grid))
    layers = pyramid_layers(base)[:max_layers]
    out = []
    for L, keys in enumerate(layers):
        for (i, j) in keys:
            out.append((L, round(i + 0.5 * L, 2), round(-(j + 0.5 * L), 2)))
    return out


def coverage_fractions(cells):
    """cells = [(layer,x,y)]. Return {cell_index: covered_fraction in [0,1]}."""
    frac = {}
    for i, (L, x, y) in enumerate(cells):
        cov = 0.0
        for (L2, x2, y2) in cells:
            if L2 > L and abs(x2 - x) < 1.0 and abs(y2 - y) < 1.0:
                cov += _rect_overlap(x, y, x2, y2)
        frac[i] = min(1.0, round(cov, 3))
    return frac


def coverage_histogram(cells):
    """Bucket coverage into {0,25,50,75,100} %. Returns dict of counts."""
    frac = coverage_fractions(cells)
    buckets = {0: 0, 25: 0, 50: 0, 75: 0, 100: 0}
    for f in frac.values():
        b = min((0, 25, 50, 75, 100), key=lambda k: abs(k - f * 100))
        buckets[b] += 1
    return buckets


def center(cells):
    if not cells:
        return cells
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2
    cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    return [(L, round(x - cx, 2), round(y - cy, 2)) for (L, x, y) in cells]
