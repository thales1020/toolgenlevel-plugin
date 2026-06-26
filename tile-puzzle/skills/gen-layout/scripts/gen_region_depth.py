"""Region-depth shape layout: DIFFERENT colour regions get DIFFERENT layer counts (per user
request — e.g. beak/eye stacked deeper than the body). Reads a colour pixel image, classifies
each cell into a region, assigns a per-region tower height, and builds per-cell towers (compose).
NOTE: this intentionally OVERRIDES the even-layers default ([9]) — depth is meant to vary here.

Usage: python gen_region_depth.py --img path.png --name duck_regions
       [--x0 24 --y0 24 --cell 89 --n 13]  [heights via HEIGHTS dict below]
"""
import sys, os, json, argparse, struct, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import claude_compose as CC
from mask_to_layout import to_stones
from geom import sym_scores, best_axis, auto_axis
from gen_layouts import structural_ok, layout_diff, to_board
from tile_level_simulator import DifficultyScorer as DS
from render_png import layout_to_png
# Pillow is imported LAZILY in read_grid — it's the only PIL user; the rest of the skill is
# deliberately stdlib-only, so a missing Pillow must not break importing this module.

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "layouts")

# per-region tower height: body thin, beak deeper, eye/mouth deepest
HEIGHTS = {"Y": 2, "O": 4, "B": 5}
REGION_RGB = {"Y": (224, 196, 60), "O": (230, 150, 40), "B": (40, 40, 40), ".": (245, 250, 253)}


def classify(r, g, b):
    if r < 80 and g < 80 and b < 80: return "B"
    if r > 210 and g > 190 and b < 140: return "Y"
    if r > 205 and 100 < g < 195 and b < 120: return "O"
    return "."


def read_grid(img, x0, y0, cell, n, classify_fn=classify):
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit("ERROR: gen_region_depth needs Pillow to read the colour image. "
                         "Install it (pip install Pillow) or pre-trace the regions by hand.")
    im = Image.open(img).convert("RGB")
    W, H = im.size
    px = im.load()
    grid = []
    for j in range(n):
        row = []
        for i in range(n):
            cx = int(x0 + (i + 0.5) * cell); cy = int(y0 + (j + 0.5) * cell)
            if not (0 <= cx < W and 0 <= cy < H):     # bounds guard (wrong x0/cell/n -> off image)
                raise SystemExit(f"ERROR: sample point ({cx},{cy}) outside image {W}x{H} at grid "
                                 f"cell ({i},{j}). Fix --x0/--y0/--cell/--n.")
            row.append(classify_fn(*px[cx, cy]))
        grid.append(row)
    return grid


def auto_detect_grid(img):
    """Best-effort grid geometry (x0,y0,cell,n) from the image: find the content bbox, estimate a
    SQUARE cell from colour-transition spacing on the central scanline. ALWAYS verify via the
    _<name>_regions.png render; override with explicit --x0/--y0/--cell/--n if off."""
    from PIL import Image
    import statistics
    im = Image.open(img).convert("RGB"); W, H = im.size; px = im.load()
    def bg(c): return min(c) > 235                       # near-white background
    step = max(1, min(W, H) // 200)
    minx, miny, maxx, maxy = W, H, 0, 0
    for y in range(0, H, step):
        for x in range(0, W, step):
            if not bg(px[x, y]):
                minx = min(minx, x); maxx = max(maxx, x); miny = min(miny, y); maxy = max(maxy, y)
    if maxx <= minx:
        raise SystemExit("ERROR: --auto found no non-background content.")
    bw, bh = maxx - minx, maxy - miny
    cy = (miny + maxy) // 2
    trans = []; lastx = minx; last = px[minx, cy]
    for x in range(minx, maxx):
        c = px[x, cy]
        if sum(abs(p - q) for p, q in zip(c, last)) > 60:
            trans.append(x - lastx); lastx = x
        last = c
    cell = int(round(statistics.median(trans))) if trans else bw // 13
    cell = max(cell, max(bw, bh) // 30, 1)               # floor so n doesn't explode
    n = max(1, round(max(bw, bh) / cell))
    x0 = minx + (bw - n * cell) // 2
    y0 = miny + (bh - n * cell) // 2
    return max(0, x0), max(0, y0), cell, n


def render_flat(cells, out, ppu=24):
    """True base-layer (L0) silhouette PNG — the shape-fidelity review (matches gen_shape_layout)."""
    l0 = [(x, y) for (L, x, y) in cells if L == 0]
    if not l0:
        return
    xs = [p[0] for p in l0]; ys = [p[1] for p in l0]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = ppu
    W = int(round((maxx - minx) * ppu)) + ppu + 2 * pad
    Hh = int(round((maxy - miny) * ppu)) + ppu + 2 * pad
    cv = [[(245, 250, 253) for _ in range(W)] for _ in range(Hh)]
    side = ppu - 1
    for (x, y) in l0:
        px0 = int(round((x - minx) * ppu)) + pad
        py0 = int(round((maxy - y) * ppu)) + pad
        for yy in range(py0, py0 + side):
            for xx in range(px0, px0 + side):
                if 0 <= yy < Hh and 0 <= xx < W:
                    cv[yy][xx] = (53, 187, 106)

    def ch(t, dd):
        cc = t + dd
        return struct.pack(">I", len(dd)) + cc + struct.pack(">I", zlib.crc32(cc) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in cv)
    png = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", W, Hh, 8, 2, 0, 0, 0))
           + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))
    open(out, "wb").write(png)


def render_regionmap(grid, heights, out, cell=26):
    """Flat map: each cell coloured by region + its height number readout printed separately."""
    n = len(grid); m = len(grid[0])
    W, H = m * cell, n * cell
    cv = [[(245, 250, 253) for _ in range(W)] for _ in range(H)]
    for j in range(n):
        for i in range(m):
            col = REGION_RGB.get(grid[j][i], (245, 250, 253))
            if grid[j][i] == ".":
                continue
            for yy in range(j * cell, j * cell + cell - 1):
                for xx in range(i * cell, i * cell + cell - 1):
                    cv[yy][xx] = col

    def ch(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in cv)
    png = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))
    open(out, "wb").write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--name", default="duck_regions")
    ap.add_argument("--x0", type=int, default=24); ap.add_argument("--y0", type=int, default=24)
    ap.add_argument("--cell", type=int, default=89); ap.add_argument("--n", type=int, default=13)
    ap.add_argument("--heights", default="",
                    help='override per-region tower heights, e.g. "Y:2,O:4,B:5" (default body/beak/eye)')
    ap.add_argument("--mirror", dest="mirror", action="store_true", default=True,
                    help="PRIORITISE symmetry (DEFAULT ON): snap to the symmetry the subject supports.")
    ap.add_argument("--no-mirror", dest="mirror", action="store_false",
                    help="do NOT force symmetry (for an asymmetric subject).")
    ap.add_argument("--axis", choices=["auto", "vertical", "horizontal", "vh", "d4"], default="auto",
                    help="auto (DEFAULT) = detect the subject's natural axes; or force 1/2/4 axes.")
    ap.add_argument("--auto", action="store_true",
                    help="auto-detect grid geometry (x0/y0/cell/n) from the image — best-effort; "
                         "VERIFY via _<name>_regions.png, override with explicit --x0/--y0/--cell/--n.")
    a = ap.parse_args()
    if a.auto:
        a.x0, a.y0, a.cell, a.n = auto_detect_grid(a.img)
        print(f"auto-detected grid: x0={a.x0} y0={a.y0} cell={a.cell} n={a.n}  (VERIFY via _regions.png)")

    heights = dict(HEIGHTS)
    if a.heights:
        for pair in a.heights.split(","):
            k, v = pair.split(":"); heights[k.strip()] = int(v)

    grid = read_grid(a.img, a.x0, a.y0, a.cell, a.n)
    print("region grid (Y=body O=beak B=eye/mouth):")
    for r in grid:
        print("  " + "".join(r))
    counts = {k: sum(row.count(k) for row in grid) for k in heights}
    print(f"region cells: {counts}  heights: {heights}")

    spec = [[i, -j, heights[grid[j][i]]] for j in range(len(grid)) for i in range(len(grid[0]))
            if grid[j][i] in heights]
    # trim_mode="shallow" PROTECTS the deep beak/eye towers (trim a shallow body edge, not the deepest
    # tops). Then PRIORITISE symmetry: auto-detect the subject's natural axes and snap that group.
    raw = CC.compose(spec, mirror=False, trim_mode="shallow")
    if a.mirror:
        from geom import d4_symmetrize, vh_symmetrize, geom_symmetrize, geom_div3_trim
        axis = auto_axis(sym_scores(raw)) if a.axis == "auto" else a.axis
        if axis == "d4":
            cells = d4_symmetrize(raw)
        elif axis == "vh":
            cells = vh_symmetrize(raw)
        elif axis in ("vertical", "horizontal"):
            cells = geom_div3_trim(geom_symmetrize(raw, axis=axis), axis=axis)
        else:
            cells = raw                               # asymmetric subject -> not forced
        print(f"symmetry axis: {a.axis} -> {axis}")
    else:
        cells = raw
    ok = structural_ok([(c[0], c[1], c[2]) for c in cells])
    d = layout_diff(cells)
    nlay = max(c[0] for c in cells) + 1
    b = to_board([(c[0], c[1], c[2]) for c in cells])
    cov = DS.cover100_by_area(b, [id(c) for c in b.all_cells()], 0.9)

    scores = sym_scores([(c[0], c[1], c[2]) for c in cells])
    bax, bscore = best_axis([(c[0], c[1], c[2]) for c in cells])
    data = to_stones([list(c) for c in cells], a.name)
    data["metadata"].update({"source": "region_depth", "layout_difficulty": round(d, 2),
                             "region_heights_requested": heights, "cover100": cov,
                             "symmetry_axes": scores, "symmetry_best_axis": bax,
                             "symmetry_score": bscore})
    path = os.path.join(OUT, f"NewLayout_{a.name}.json")
    json.dump(data, open(path, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    render_regionmap(grid, heights, os.path.join(OUT, f"_{a.name}_regions.png"))
    render_flat([(c[0], c[1], c[2]) for c in cells], os.path.join(OUT, f"_{a.name}_flat.png"))
    layout_to_png(path, os.path.join(OUT, f"_{a.name}_stack.png"), ppu=18)
    print(f"-> {path}")
    print(f"   total={len(cells)} layers={nlay} cover100={cov} diff={d:.2f} ok={ok}")
    sym_str = "  ".join(f"{k[:4]}={v:.2f}" for k, v in scores.items())
    print(f"   symmetry: {sym_str}  -> best {bax}={bscore:.2f}" + ("  [mirrored]" if a.mirror else ""))
    print(f"   review: _{a.name}_regions.png (segmentation)  _{a.name}_flat.png (L0 silhouette)  "
          f"_{a.name}_stack.png (depth)")


if __name__ == "__main__":
    main()
