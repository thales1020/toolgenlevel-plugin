"""Industrial layout-gen — abstract shape families + transforms + dedup signature.

For BULK empty-layout generation (branch A): we do NOT force recognizable icons
(research: studios use abstract boards at scale, not silhouettes). Diversity comes
from a small set of parametric families crossed with transforms + parameter sweeps.

A "grid" here = list of rows of 0/1 (1 = filled cell). Pure stdlib.
"""
import math


# ---------- parametric families (grid = list[list[0/1]]) ----------
def circle(R):
    G = 2 * R + 1; c = R
    return [[1 if math.hypot(x - c, y - c) <= R + 0.3 else 0 for x in range(G)] for y in range(G)]

def square(S):
    return [[1] * S for _ in range(S)]

def rect(W, H):
    return [[1] * W for _ in range(H)]

def diamond(R):
    G = 2 * R + 1; c = R
    return [[1 if abs(x - c) + abs(y - c) <= R else 0 for x in range(G)] for y in range(G)]

def hexagon(R):
    G = 2 * R + 1; c = R
    return [[1 if (abs(y - c) <= R and abs(x - c) <= R - abs(y - c) * 0.5 + 0.5) else 0
             for x in range(G)] for y in range(G)]

def triangle(H):
    return [[1 if abs(x - (H - 1)) <= y else 0 for x in range(2 * H - 1)] for y in range(H)]

def ring(R, r):
    G = 2 * R + 1; c = R
    return [[1 if r <= math.hypot(x - c, y - c) <= R + 0.3 else 0 for x in range(G)] for y in range(G)]

def oval(RX, RY):
    G = 2 * RX + 1; H = 2 * RY + 1
    return [[1 if ((x - RX) / RX) ** 2 + ((y - RY) / RY) ** 2 <= 1.05 else 0
             for x in range(G)] for y in range(H)]

def plus(S, t):
    lo = (S - t) // 2; hi = lo + t
    return [[1 if (lo <= x < hi or lo <= y < hi) else 0 for x in range(S)] for y in range(S)]

def octagon(R):
    G = 2 * R + 1; c = R; cut = R // 2
    return [[1 if (abs(x - c) <= R and abs(y - c) <= R and abs(x - c) + abs(y - c) <= R + cut) else 0
             for x in range(G)] for y in range(G)]

def trapezoid(top, bot, H):
    out = []
    for y in range(H):
        w = round(top + (bot - top) * y / (H - 1)); pad = (bot - w) // 2
        out.append([1 if pad <= x < pad + w else 0 for x in range(bot)])
    return out


# ---- SPARSE / SCATTERED families (match real boards: fill ~0.46, small base, deep-but-easy) ----
def scattered(rng, w=9, h=11, n_clusters=4, h_sym=True):
    """Place a few small 2x2/2x3 blocks with gaps -> sparse base (fill ~0.4-0.5).
    Stacked deep, low per-cell coverage -> 'deep but easy' (matches competitor)."""
    g = [[0] * w for _ in range(h)]
    left = w // 2 - 1                                # place strictly in left zone -> central gap kept
    for _ in range(n_clusters):
        bw = rng.choice([2, 2, 3]); bh = rng.choice([2, 3])
        cx = rng.randint(0, max(0, left - bw)); cy = rng.randint(0, max(0, h - bh))
        for yy in range(cy, min(h, cy + bh)):
            for xx in range(cx, min(left, cx + bw)):
                g[yy][xx] = 1
                if h_sym:
                    g[yy][w - 1 - xx] = 1            # mirror -> horizontal symmetry, sparse middle
    return g


def sparse_lattice(rng, w=9, h=11, keep=0.55):
    """A spaced lattice of 2x2 tiles with holes -> sparse, h-symmetric, regular."""
    g = [[0] * w for _ in range(h)]
    half = w // 2 + 1
    for by in range(0, h - 1, 3):
        for bx in range(0, half - 1, 3):
            if rng.random() < keep:
                for yy in (by, by + 1):
                    for xx in (bx, bx + 1):
                        if yy < h and xx < w:
                            g[yy][xx] = 1; g[yy][w - 1 - xx] = 1
    return g


def frame(rng, w=9, h=11, t=2):
    """A hollow frame/border -> sparse interior (hole), deep-but-easy when stacked."""
    g = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if x < t or x >= w - t or y < t or y >= h - t:
                g[y][x] = 1
    return g


def spaced_clusters(rng, n_clusters=5, block=2, gap=1, h_sym=True, cols=3, rows=4):
    """CALIBRATED real-match base: n separated block×block clusters, h-symmetric.
    Verified: with build(keep_upper=0.9), diff-by-depth matches real boards (meanErr 0.38),
    and 5 clusters independently == the real median cluster count. See LAYOUT_PRIORS.md.
    NOTE: build these with `LB.build(grid, keep_upper=0.9)` to hit the real difficulty curve."""
    step = block + gap
    w = cols * step; h = rows * step
    g = [[0] * w for _ in range(h)]
    slots = [(r, c) for r in range(rows) for c in range(cols // 2 + 1)]
    rng.shuffle(slots)
    for (r, c) in slots[:n_clusters]:
        y0 = r * step; x0 = c * step
        for yy in range(y0, min(h, y0 + block)):
            for xx in range(x0, min(w, x0 + block)):
                g[yy][xx] = 1
                if h_sym: g[yy][w - 1 - xx] = 1
    rowsnz = [i for i, row in enumerate(g) if any(row)]
    colsnz = [j for j in range(w) if any(g[i][j] for i in range(h))]
    if not rowsnz: return [[0]]
    return [[g[i][j] for j in range(min(colsnz), max(colsnz) + 1)] for i in range(min(rowsnz), max(rowsnz) + 1)]

# CALIBRATED build knob for real-match: depth ~6, keep_upper=0.9
REAL_MATCH = {"family": spaced_clusters, "keep_upper": 0.9, "depth_default": 6}


# family -> a sampler(rng) returning a grid; rng is a random.Random
FAMILIES = {
    "circle":   lambda r: circle(r.randint(5, 9)),
    "square":   lambda r: square(r.randint(9, 14)),
    "rect":     lambda r: rect(r.randint(9, 15), r.randint(7, 12)),
    "diamond":  lambda r: diamond(r.randint(6, 10)),
    "hexagon":  lambda r: hexagon(r.randint(5, 9)),
    "triangle": lambda r: triangle(r.randint(10, 15)),
    "ring":     lambda r: ring(r.randint(7, 10), r.randint(2, 4)),
    "oval":     lambda r: oval(r.randint(7, 10), r.randint(5, 8)),
    "plus":     lambda r: plus(r.randint(11, 15), r.randint(4, 6)),
    "octagon":  lambda r: octagon(r.randint(6, 9)),
    "trapezoid":lambda r: trapezoid(r.randint(5, 8), r.randint(13, 17), r.randint(10, 13)),
    # sparse families — match real boards (deep but easy, fill ~0.46, h-symmetric)
    "scattered":     lambda r: scattered(r, n_clusters=r.randint(3, 5)),
    "sparse_lattice":lambda r: sparse_lattice(r, keep=r.choice([0.5, 0.6, 0.7])),
    "frame":         lambda r: frame(r, t=r.randint(2, 3)),
    # CALIBRATED real-match family (build with keep_upper=0.9) — matches real diff curve + size
    "real_match":    lambda r: spaced_clusters(r, n_clusters=r.randint(3, 5)),
}


# ---------- transforms ----------
def _dims(g):
    return len(g), (len(g[0]) if g else 0)

def rot90(g):
    h, w = _dims(g)
    return [[g[h - 1 - x][y] for x in range(h)] for y in range(w)]

def mirror_h(g):
    return [row[::-1] for row in g]

def mirror_v(g):
    return g[::-1]

def punch_holes(g, rng, n=1):
    """Carve n small interior holes (ring-like variety). Avoids the outer ring."""
    h, w = _dims(g)
    g = [row[:] for row in g]
    interior = [(y, x) for y in range(2, h - 2) for x in range(2, w - 2) if g[y][x]]
    if not interior:
        return g
    for _ in range(n):
        cy, cx = rng.choice(interior)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if 0 <= cy + dy < h and 0 <= cx + dx < w:
                    g[cy + dy][cx + dx] = 0
    return g

def jitter_edge(g, rng, k=3):
    """Remove k random boundary cells -> asymmetric variation (kept connected-ish)."""
    h, w = _dims(g)
    g = [row[:] for row in g]
    def is_edge(y, x):
        if not g[y][x]:
            return False
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if not (0 <= ny < h and 0 <= nx < w) or not g[ny][nx]:
                return True
        return False
    edges = [(y, x) for y in range(h) for x in range(w) if is_edge(y, x)]
    rng.shuffle(edges)
    for y, x in edges[:k]:
        g[y][x] = 0
    return g

def blend(g1, g2, dx=0, dy=0):
    """Union two grids with an offset -> compound shapes."""
    h = max(len(g1), len(g2) + dy)
    w = max(len(g1[0]), len(g2[0]) + dx)
    out = [[0] * w for _ in range(h)]
    for y, row in enumerate(g1):
        for x, v in enumerate(row):
            if v:
                out[y][x] = 1
    for y, row in enumerate(g2):
        for x, v in enumerate(row):
            if v and 0 <= y + dy < h and 0 <= x + dx < w:
                out[y + dy][x + dx] = 1
    return out

TRANSFORMS = ["none", "rot90", "mirror_h", "mirror_v", "punch_holes", "jitter_edge"]

def apply_transform(g, name, rng):
    if name == "none": return g
    if name == "rot90": return rot90(g)
    if name == "mirror_h": return mirror_h(g)
    if name == "mirror_v": return mirror_v(g)
    if name == "punch_holes": return punch_holes(g, rng, n=rng.randint(1, 2))
    if name == "jitter_edge": return jitter_edge(g, rng, k=rng.randint(2, 5))
    return g


# ---------- diversity / dedup ----------
def exact_sig(cells):
    """Exact signature: frozenset of (layer, round x, round y). Identical layouts collide."""
    return frozenset((c[0], round(c[1], 1), round(c[2], 1)) for c in cells)

def coarse_sig(cells, cov_hist):
    """Near-dup bucket: (n_layers, total rounded to 6, bbox WxH, coverage-hist tuple).
    Two layouts in the same bucket are 'too similar' -> keep only one."""
    layers = max(c[0] for c in cells) + 1
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    bw = round((max(xs) - min(xs)))
    bh = round((max(ys) - min(ys)))
    tot = (len(cells) // 6) * 6
    ch = tuple(cov_hist[k] // 8 for k in (0, 25, 50, 75, 100))
    return (layers, tot, bw, bh, ch)
