"""Shared mask operations — pure stdlib, no deps.

A "mask" = list of strings (rows) using '#' (filled) and '.' (empty), OR a 2D
list of 0/1. Helpers: load/save, bounding box, connected components, erosion,
background flood-fill (holes), perimeter, and the pyramid-support simulation
(single source of truth shared by evaluate_icon + mask_to_layout).
"""
import os


def load_mask(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            # a mask data row contains ONLY '#' and '.'; anything else is a comment/header
            if set(line) - {"#", "."}:
                continue
            rows.append([1 if ch == "#" else 0 for ch in line])
    w = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([0] * (w - len(r)))
    return rows


def save_mask(grid, path, header=None):
    with open(path, "w", encoding="utf-8") as f:
        if header:
            f.write(f"# {header}\n")
        for row in grid:
            f.write("".join("#" if c else "." for c in row) + "\n")


def dims(grid):
    return (len(grid), len(grid[0]) if grid else 0)  # (h, w)


def count_on(grid):
    return sum(sum(r) for r in grid)


def bounding_box(grid):
    h, w = dims(grid)
    xs = [x for y in range(h) for x in range(w) if grid[y][x]]
    ys = [y for y in range(h) for x in range(w) if grid[y][x]]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))  # x0,y0,x1,y1


def crop_to_content(grid, pad=0):
    bb = bounding_box(grid)
    if not bb:
        return grid
    x0, y0, x1, y1 = bb
    h, w = dims(grid)
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad)
    x1 = min(w - 1, x1 + pad); y1 = min(h - 1, y1 + pad)
    return [row[x0:x1 + 1] for row in grid[y0:y1 + 1]]


def connected_components(grid, conn=4):
    """Return list of components (each a set of (x,y)) of filled cells."""
    h, w = dims(grid)
    seen = [[False] * w for _ in range(h)]
    comps = []
    nbrs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if conn == 8:
        nbrs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    for sy in range(h):
        for sx in range(w):
            if grid[sy][sx] and not seen[sy][sx]:
                stack = [(sx, sy)]; seen[sy][sx] = True; comp = set()
                while stack:
                    x, y = stack.pop(); comp.add((x, y))
                    for dx, dy in nbrs:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True; stack.append((nx, ny))
                comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def keep_largest(grid):
    comps = connected_components(grid)
    if len(comps) <= 1:
        return grid
    keep = comps[0]
    h, w = dims(grid)
    return [[1 if (x, y) in keep else 0 for x in range(w)] for y in range(h)]


def erode(grid, conn=4):
    """One erosion pass: a cell stays ON iff all its 4 (or 8) neighbours are ON."""
    h, w = dims(grid)
    nbrs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if conn == 8:
        nbrs += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if not grid[y][x]:
                continue
            ok = True
            for dx, dy in nbrs:
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h and grid[ny][nx]):
                    ok = False; break
            out[y][x] = 1 if ok else 0
    return out


def hole_count(grid):
    """# of background regions NOT connected to the border (interior holes)."""
    h, w = dims(grid)
    bg = [[grid[y][x] == 0 for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    # flood from border
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if bg[y][x] and not seen[y][x]:
                seen[y][x] = True; stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if bg[y][x] and not seen[y][x]:
                seen[y][x] = True; stack.append((x, y))
    while stack:
        x, y = stack.pop()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and bg[ny][nx] and not seen[ny][nx]:
                seen[ny][nx] = True; stack.append((nx, ny))
    # remaining unseen bg cells = holes; count distinct regions
    holes = 0
    for sy in range(h):
        for sx in range(w):
            if bg[sy][sx] and not seen[sy][sx]:
                holes += 1
                st = [(sx, sy)]; seen[sy][sx] = True
                while st:
                    x, y = st.pop()
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < w and 0 <= ny < h and bg[ny][nx] and not seen[ny][nx]:
                            seen[ny][nx] = True; st.append((nx, ny))
    return holes


def fill_holes(grid):
    """Fill interior background regions (holes) so the silhouette is solid —
    holes (e.g. a leaf's vein) make ugly gaps in a layout. Flood bg from border;
    any bg not reached = hole -> set ON."""
    h, w = dims(grid)
    bg_reach = [[False] * w for _ in range(h)]
    stack = []
    for x in range(w):
        for y in (0, h - 1):
            if grid[y][x] == 0 and not bg_reach[y][x]:
                bg_reach[y][x] = True; stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if grid[y][x] == 0 and not bg_reach[y][x]:
                bg_reach[y][x] = True; stack.append((x, y))
    while stack:
        x, y = stack.pop()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == 0 and not bg_reach[ny][nx]:
                bg_reach[ny][nx] = True; stack.append((nx, ny))
    return [[1 if (grid[y][x] or not bg_reach[y][x]) else 0 for x in range(w)] for y in range(h)]


def perimeter(grid):
    """Count filled-cell edges adjacent to empty/outside."""
    h, w = dims(grid)
    p = 0
    for y in range(h):
        for x in range(w):
            if not grid[y][x]:
                continue
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h and grid[ny][nx]):
                    p += 1
    return p


def min_feature_width(grid):
    """~min stroke width via repeated erosion until the shape vanishes."""
    g = [row[:] for row in grid]
    passes = 0
    while count_on(g) > 0:
        g = erode(g)
        passes += 1
        if passes > 200:
            break
    return 2 * passes - 1 if passes > 0 else 0


def convex_hull(points):
    """Andrew's monotone chain. points = list of (x,y). Returns hull polygon."""
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def polygon_area(poly):
    n = len(poly)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def solidity(grid):
    """ON-area / convex-hull-area. ~1 = convex (hexagon/triangle); <1 = concave/lobed
    (heart/star/crescent). Drives auto-grid: more concave -> needs higher resolution."""
    h, w = dims(grid)
    pts = [(x, y) for y in range(h) for x in range(w) if grid[y][x]]
    on = len(pts)
    if on < 3:
        return 1.0
    hull = convex_hull(pts)
    # +on*0.5 boundary correction (Pick-ish) so a solid convex block reads ~1.0
    ha = polygon_area(hull) + 0.5 * len(hull) + 1
    return min(1.0, on / ha) if ha else 1.0


def pyramid_layers(base_set):
    """Mahjong-pyramid support sim. base_set = set of (col,row) ON cells (layer 0).
    Layer L+1 cell at integer key (i,j) (representing float (i+0.5*par, j+0.5*par))
    exists iff its 4 supporting cells in layer L are present.

    We track each layer as a set of integer (i,j) keys in that layer's own lattice.
    A layer-(L+1) cell sits over layer-L cells (i,j),(i+1,j),(i,j+1),(i+1,j+1).
    Returns list of layers; each = set of (i,j) integer keys.
    """
    layers = [set(base_set)]
    cur = set(base_set)
    while True:
        nxt = set()
        for (i, j) in cur:
            # candidate above-right diagonal: needs (i,j),(i+1,j),(i,j+1),(i+1,j+1)
            if (i + 1, j) in cur and (i, j + 1) in cur and (i + 1, j + 1) in cur:
                nxt.add((i, j))
        if not nxt:
            break
        layers.append(nxt)
        cur = nxt
        if len(layers) > 64:
            break
    return layers
