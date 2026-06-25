"""SVG -> binary mask, pure stdlib (no Pillow/cairo).

Parses <path>/<circle>/<rect>/<ellipse>/<polygon> into polygons (flattening
beziers + arcs), rasterizes with an even-odd scanline fill at supersampled
resolution, then downsamples to a target grid -> '#'/'.' mask.

Usage:
  python svg_to_mask.py --in icon.svg --out icon.mask.txt [--grid 18] [--coverage 0.5]
  python svg_to_mask.py --svg "<svg ...>...</svg>" --out icon.mask.txt
"""
import sys, os, re, math, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from maskio import save_mask, crop_to_content, keep_largest, fill_holes, hole_count

NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _nums(s):
    return [float(x) for x in NUM.findall(s)]


def _flatten_cubic(p0, p1, p2, p3, n=18):
    pts = []
    for k in range(1, n + 1):
        t = k / n; mt = 1 - t
        x = mt**3*p0[0] + 3*mt*mt*t*p1[0] + 3*mt*t*t*p2[0] + t**3*p3[0]
        y = mt**3*p0[1] + 3*mt*mt*t*p1[1] + 3*mt*t*t*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


def _flatten_quad(p0, p1, p2, n=14):
    pts = []
    for k in range(1, n + 1):
        t = k / n; mt = 1 - t
        x = mt*mt*p0[0] + 2*mt*t*p1[0] + t*t*p2[0]
        y = mt*mt*p0[1] + 2*mt*t*p1[1] + t*t*p2[1]
        pts.append((x, y))
    return pts


def _arc(p0, rx, ry, phi, large, sweep, p1, n=24):
    """SVG elliptical arc endpoint -> sampled points (standard conversion)."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    phi = math.radians(phi)
    cphi, sphi = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0]-p1[0])/2, (p0[1]-p1[1])/2
    x1p = cphi*dx + sphi*dy; y1p = -sphi*dx + cphi*dy
    rx, ry = abs(rx), abs(ry)
    lam = x1p*x1p/(rx*rx) + y1p*y1p/(ry*ry)
    if lam > 1:
        s = math.sqrt(lam); rx *= s; ry *= s
    num = rx*rx*ry*ry - rx*rx*y1p*y1p - ry*ry*x1p*x1p
    den = rx*rx*y1p*y1p + ry*ry*x1p*x1p
    co = math.sqrt(max(0, num/den)) if den else 0
    if large == sweep:
        co = -co
    cxp = co*rx*y1p/ry; cyp = -co*ry*x1p/rx
    cx = cphi*cxp - sphi*cyp + (p0[0]+p1[0])/2
    cy = sphi*cxp + cphi*cyp + (p0[1]+p1[1])/2

    def ang(ux, uy, vx, vy):
        d = math.hypot(ux, uy)*math.hypot(vx, vy)
        c = max(-1, min(1, (ux*vx+uy*vy)/d)) if d else 1
        a = math.acos(c)
        if ux*vy - uy*vx < 0:
            a = -a
        return a
    th0 = ang(1, 0, (x1p-cxp)/rx, (y1p-cyp)/ry)
    dth = ang((x1p-cxp)/rx, (y1p-cyp)/ry, (-x1p-cxp)/rx, (-y1p-cyp)/ry)
    if not sweep and dth > 0:
        dth -= 2*math.pi
    elif sweep and dth < 0:
        dth += 2*math.pi
    pts = []
    for k in range(1, n + 1):
        th = th0 + dth*k/n
        x = cphi*rx*math.cos(th) - sphi*ry*math.sin(th) + cx
        y = sphi*rx*math.cos(th) + cphi*ry*math.sin(th) + cy
        pts.append((x, y))
    return pts


def parse_path(d):
    """Parse path 'd' -> list of subpaths (each a list of (x,y))."""
    tokens = re.findall(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?", d)
    subs = []; cur = []; pos = (0.0, 0.0); start = (0.0, 0.0)
    prev_c2 = None; prev_q1 = None; cmd = None; i = 0
    def rd(n):
        nonlocal i
        vals = tokens[i:i+n]; i += n
        return [float(v) for v in vals]
    while i < len(tokens):
        t = tokens[i]
        if re.match(r"[A-Za-z]", t):
            cmd = t; i += 1
        rel = cmd.islower(); C = cmd.upper()
        if C == "M":
            x, y = rd(2)
            if rel: x += pos[0]; y += pos[1]
            if cur: subs.append(cur)
            cur = [(x, y)]; pos = (x, y); start = (x, y); cmd = "l" if rel else "L"
        elif C == "L":
            x, y = rd(2)
            if rel: x += pos[0]; y += pos[1]
            cur.append((x, y)); pos = (x, y)
        elif C == "H":
            x = rd(1)[0]
            if rel: x += pos[0]
            cur.append((x, pos[1])); pos = (x, pos[1])
        elif C == "V":
            y = rd(1)[0]
            if rel: y += pos[1]
            cur.append((pos[0], y)); pos = (pos[0], y)
        elif C == "C":
            x1, y1, x2, y2, x, y = rd(6)
            if rel: x1+=pos[0];y1+=pos[1];x2+=pos[0];y2+=pos[1];x+=pos[0];y+=pos[1]
            cur += _flatten_cubic(pos, (x1, y1), (x2, y2), (x, y))
            prev_c2 = (x2, y2); pos = (x, y)
        elif C == "S":
            x2, y2, x, y = rd(4)
            if rel: x2+=pos[0];y2+=pos[1];x+=pos[0];y+=pos[1]
            c1 = (2*pos[0]-prev_c2[0], 2*pos[1]-prev_c2[1]) if prev_c2 else pos
            cur += _flatten_cubic(pos, c1, (x2, y2), (x, y))
            prev_c2 = (x2, y2); pos = (x, y)
        elif C == "Q":
            x1, y1, x, y = rd(4)
            if rel: x1+=pos[0];y1+=pos[1];x+=pos[0];y+=pos[1]
            cur += _flatten_quad(pos, (x1, y1), (x, y))
            prev_q1 = (x1, y1); pos = (x, y)
        elif C == "T":
            x, y = rd(2)
            if rel: x+=pos[0];y+=pos[1]
            q1 = (2*pos[0]-prev_q1[0], 2*pos[1]-prev_q1[1]) if prev_q1 else pos
            cur += _flatten_quad(pos, q1, (x, y))
            prev_q1 = q1; pos = (x, y)
        elif C == "A":
            rx, ry, rot, large, sweep, x, y = rd(7)
            if rel: x+=pos[0]; y+=pos[1]
            cur += _arc(pos, rx, ry, rot, int(large), int(sweep), (x, y))
            pos = (x, y)
        elif C == "Z":
            if cur:
                cur.append(start); subs.append(cur); cur = []
            pos = start
        else:
            i += 1
        if C not in ("C", "S"): prev_c2 = None
        if C not in ("Q", "T"): prev_q1 = None
    if cur:
        subs.append(cur)
    return subs


def _circle_poly(cx, cy, r, n=48):
    return [[(cx + r*math.cos(2*math.pi*k/n), cy + r*math.sin(2*math.pi*k/n)) for k in range(n)]]


def _ellipse_poly(cx, cy, rx, ry, n=48):
    return [[(cx + rx*math.cos(2*math.pi*k/n), cy + ry*math.sin(2*math.pi*k/n)) for k in range(n)]]


# ---- attribute extraction (quote-agnostic: matches "..." OR '...') ----
def _attrs(tag):
    """Parse an element's attributes -> dict, accepting single OR double quotes.
    (re.findall yields '' — not None — for the non-matching quote alternative.)"""
    # exactly one quote alternative matches; the other group is '' (re.findall never
    # yields None), so `v1 or v2` selects the populated one for any non-empty value.
    return {k: (v1 or v2)
            for k, v1, v2 in re.findall(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', tag)}


# ---- affine transforms ----
IDENT = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)  # (a, b, c, d, e, f): x' = a*x + c*y + e, y' = b*x + d*y + f


def _mat_mul(m1, m2):
    a1, b1, c1, d1, e1, f1 = m1
    a2, b2, c2, d2, e2, f2 = m2
    return (a1*a2 + c1*b2,        b1*a2 + d1*b2,
            a1*c2 + c1*d2,        b1*c2 + d1*d2,
            a1*e2 + c1*f2 + e1,   b1*e2 + d1*f2 + f1)


def _parse_transform(s):
    """Parse an SVG transform string into a single affine matrix.
    Supports translate / scale / matrix / rotate (incl. rotate about a point)."""
    m = IDENT
    if not s:
        return m
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", s):
        v = _nums(args)
        if name == "translate":
            tx = v[0] if v else 0.0
            ty = v[1] if len(v) > 1 else 0.0
            m = _mat_mul(m, (1, 0, 0, 1, tx, ty))
        elif name == "scale":
            sx = v[0] if v else 1.0
            sy = v[1] if len(v) > 1 else sx
            m = _mat_mul(m, (sx, 0, 0, sy, 0, 0))
        elif name == "matrix" and len(v) == 6:
            m = _mat_mul(m, tuple(v))
        elif name == "rotate" and v:
            ang = math.radians(v[0]); ca, sa = math.cos(ang), math.sin(ang)
            if len(v) >= 3:  # rotate around (cx, cy)
                cx, cy = v[1], v[2]
                m = _mat_mul(m, (1, 0, 0, 1, cx, cy))
                m = _mat_mul(m, (ca, sa, -sa, ca, 0, 0))
                m = _mat_mul(m, (1, 0, 0, 1, -cx, -cy))
            else:
                m = _mat_mul(m, (ca, sa, -sa, ca, 0, 0))
    return m


def _apply(m, pts):
    a, b, c, d, e, f = m
    return [(a*x + c*y + e, b*x + d*y + f) for x, y in pts]


def _fill_is_none(attrs):
    """True if the element is explicitly fill:none (attribute or style)."""
    fill = attrs.get("fill")
    style = attrs.get("style", "")
    ms = re.search(r"fill\s*:\s*([^;]+)", style)
    if ms:
        fill = ms.group(1).strip()
    return fill is not None and fill.strip().lower() == "none"


def svg_to_polygons(svg):
    """Return list of (polygon_points, fill_none) — fill_none flags stroke-only paths.

    Walks the SVG token stream so nested <g transform=...> matrices compose and
    apply to each shape's points. Attribute parsing is quote-agnostic.
    """
    polys = []
    # transform stack: list of (matrix, depth_of_open_g) — popped on matching </g>
    stack = []  # entries: matrix
    depth = 0   # current <g> nesting depth

    def cur_mat():
        m = IDENT
        for sm in stack:
            m = _mat_mul(m, sm)
        return m

    # Tokenize into <g>, </g>, and self-contained shape elements, in document order.
    tok = re.compile(
        r"<g\b[^>]*>|</g\s*>|<(?:path|circle|ellipse|rect|polygon|polyline)\b[^>]*/?>",
        re.IGNORECASE)
    for mt in tok.finditer(svg):
        tag = mt.group(0)
        low = tag.lower()
        if low.startswith("<g"):
            ga = _attrs(tag)
            stack.append(_parse_transform(ga.get("transform", "")))
            depth += 1
            continue
        if low.startswith("</g"):
            if stack:
                stack.pop()
            depth = max(0, depth - 1)
            continue
        a = _attrs(tag)
        gm = cur_mat()
        em = _mat_mul(gm, _parse_transform(a.get("transform", "")))
        fn = _fill_is_none(a)
        shape = []  # list of point-lists for this element
        name = re.match(r"<(\w+)", low).group(1)
        if name == "path" and "d" in a:
            shape = parse_path(a["d"])
        elif name == "circle" and "r" in a:
            shape = _circle_poly(float(a.get("cx", 0)), float(a.get("cy", 0)), float(a["r"]))
        elif name == "ellipse":
            shape = _ellipse_poly(float(a.get("cx", 0)), float(a.get("cy", 0)),
                                  float(a.get("rx", 1)), float(a.get("ry", 1)))
        elif name == "rect":
            x, y = float(a.get("x", 0)), float(a.get("y", 0))
            w, h = float(a.get("width", 0)), float(a.get("height", 0))
            shape = [[(x, y), (x+w, y), (x+w, y+h), (x, y+h)]]
        elif name in ("polygon", "polyline") and "points" in a:
            n = _nums(a["points"])
            shape = [[(n[k], n[k+1]) for k in range(0, len(n)-1, 2)]]
        for poly in shape:
            polys.append((_apply(em, poly), fn))
    return polys


def _viewbox(svg):
    m = re.search(r'viewBox\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', svg)
    if m:
        v = _nums(m.group(1) if m.group(1) is not None else m.group(2))
        if len(v) == 4:
            return v
    wm = re.search(r"\bwidth\s*=\s*['\"]([\d.]+)", svg)
    hm = re.search(r"\bheight\s*=\s*['\"]([\d.]+)", svg)
    w = float(wm.group(1)) if wm else 24.0
    h = float(hm.group(1)) if hm else 24.0
    return [0, 0, w, h]


def _strip_fillnone(polys):
    """polys is list of (points, fill_none) tuples. Drop fill:none polygons, but if
    that empties everything, keep them all + warn (full stroke rendering is out of scope)."""
    kept = [(p, fn) for p, fn in polys if not fn]
    if not kept and polys:
        sys.stderr.write("WARN: all paths fill:none — filled as solid; "
                         "trace manually for outline icons\n")
        return [p for p, fn in polys]
    return [p for p, fn in kept]


def rasterize(polys, vb, grid=18, supersample=6, coverage=0.5):
    """Even-odd scanline fill at grid*ss, then downsample by coverage -> 0/1 grid.

    polys accepts either bare point-lists OR (points, fill_none) tuples; fill:none
    polygons are skipped (see _strip_fillnone) unless that would empty the mask."""
    # polys may be (points, fill_none) tuples (new) or bare point-lists (legacy callers)
    if polys and isinstance(polys[0], tuple) and len(polys[0]) == 2 \
            and isinstance(polys[0][1], bool):
        polys = _strip_fillnone(polys)
    vx, vy, vw, vh = vb
    if vw <= 0 or vh <= 0:
        return [[0]]
    # keep aspect: target grid width = grid, height scaled
    gw = grid
    gh = max(1, round(grid * vh / vw))
    R = supersample
    W, H = gw * R, gh * R
    sx = W / vw; sy = H / vh
    # build edges in device space
    edges = []  # (ymin, ymax, x_at_ymin, dxdy)
    for poly in polys:
        if len(poly) < 2:
            continue
        pts = [((px - vx) * sx, (py - vy) * sy) for px, py in poly]
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        for k in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            if y0 == y1:
                continue
            if y0 > y1:
                x0, y0, x1, y1 = x1, y1, x0, y0
            edges.append((y0, y1, x0, (x1 - x0) / (y1 - y0)))
    hi = [[0] * W for _ in range(H)]
    for py in range(H):
        yc = py + 0.5
        xs = [e[2] + (yc - e[0]) * e[3] for e in edges if e[0] <= yc < e[1]]
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            xa = max(0, int(math.ceil(xs[k] - 0.5)))
            xb = min(W - 1, int(math.floor(xs[k + 1] - 0.5)))
            for px in range(xa, xb + 1):
                hi[py][px] = 1
    # downsample by coverage
    out = [[0] * gw for _ in range(gh)]
    cell = R * R
    for gy in range(gh):
        for gx in range(gw):
            c = 0
            for yy in range(gy * R, gy * R + R):
                row = hi[yy]
                for xx in range(gx * R, gx * R + R):
                    c += row[xx]
            out[gy][gx] = 1 if c / cell >= coverage else 0
    return out


def svg_string_to_mask(svg, grid=18, coverage=0.5, supersample=6, clean=True, fill=False):
    """clean = drop stray disconnected pixels (keep_largest) — safe rasterizer-artifact
    cleanup, ON by default. fill = fill interior holes — DESTRUCTIVE for ring/donut shapes
    where the hole IS the shape, so OFF by default. Claude decides whether to fill after
    reviewing the rendered mask (a leaf-vein hole -> fill; a donut hole -> keep)."""
    polys = svg_to_polygons(svg)
    vb = _viewbox(svg)
    grid_cells = rasterize(polys, vb, grid=grid, supersample=supersample, coverage=coverage)
    if clean:
        grid_cells = keep_largest(grid_cells)   # drop stray disconnected pixels (rasterizer artifact)
    if fill:
        grid_cells = fill_holes(grid_cells)      # ONLY when Claude judges the hole is an artifact
    return crop_to_content(grid_cells)


def _iou_vs_ref(small, ref):
    """IoU of `small` (nearest-upscaled) vs high-res `ref` grid."""
    rh = len(ref); rw = len(ref[0])
    sh = len(small); sw = len(small[0]) if sh else 0
    if sw == 0:
        return 0.0
    inter = union = 0
    for Y in range(rh):
        sy = min(sh - 1, Y * sh // rh)
        for X in range(rw):
            sx = min(sw - 1, X * sw // rw)
            a = ref[Y][X]; b = small[sy][sx]
            if a or b:
                union += 1
                if a and b:
                    inter += 1
    return inter / union if union else 0.0


def pick_grid(svg, grids=(10, 12, 14, 16, 18, 20), target_iou=0.92, step=4):
    """Smallest grid where the shape has CONVERGED: IoU(grid G, grid G+step) >= target.
    Compares consecutive resolutions, so it measures feature-stability (lobes/holes
    appearing) NOT curve-smoothness — a triangle converges early (stays small),
    a heart needs higher grid until its two humps stabilize. Returns (grid, iou)."""
    polys = svg_to_polygons(svg)
    vb = _viewbox(svg)
    cache = {}
    def m(g):
        if g not in cache:
            cache[g] = crop_to_content(rasterize(polys, vb, grid=g, supersample=6))
        return cache[g]
    best = (grids[-1], 0.0)
    for g in grids:
        iou = _iou_vs_ref(m(g), m(g + step))   # m(g) upscaled to m(g+step) res
        if iou >= target_iou:
            return g, round(iou, 3)
        if iou > best[1]:
            best = (g, round(iou, 3))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--svg", dest="svg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--grid", type=int, default=18)
    ap.add_argument("--coverage", type=float, default=0.5)
    ap.add_argument("--supersample", type=int, default=6)
    ap.add_argument("--fill-holes", dest="fill", action="store_true",
                    help="fill interior holes -> solid silhouette. OFF by default; "
                         "set ONLY when Claude judges the hole is a rasterizer artifact "
                         "(e.g. leaf vein), NOT for ring/donut shapes where the hole is the shape.")
    ap.add_argument("--no-keep-largest", dest="clean", action="store_false",
                    help="keep stray disconnected pixels (default drops them)")
    a = ap.parse_args()
    if a.svg:
        svg = a.svg
    else:
        with open(a.inp, encoding="utf-8") as f:
            svg = f.read()
    grid = svg_string_to_mask(svg, a.grid, a.coverage, a.supersample, clean=a.clean, fill=a.fill)
    save_mask(grid, a.out, header=f"grid: {len(grid[0])}x{len(grid)}  src: svg")
    on = sum(sum(r) for r in grid)
    holes = hole_count(grid)
    print(f"SAVED {a.out}  {len(grid[0])}x{len(grid)}  ON={on}  holes={holes}  fill_holes={'on' if a.fill else 'OFF'}")
    if holes and not a.fill:
        print(f"  NOTE: {holes} interior hole(s) kept. Claude: review the render - if a hole is an "
              f"artifact, re-run with --fill-holes; if intentional (donut/ring), keep as-is.")


if __name__ == "__main__":
    main()
