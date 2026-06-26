"""Shape -> clean multi-layer layout, the AESTHETIC path (use this for icon/animal/logo shapes
instead of compose() isolated +0.5 towers, which fringe the silhouette into a checkerboard).

Pipeline (decoupled silhouette vs depth, per EXPERIENCES [8]):
  mask  --(capped_inset support)-->  cells   # rim stays 1 layer -> silhouette crisp; depth insets toward centre
  peel exposed top cells (farthest first, never a supporter, never the base) --> exact target count
  -> NewLayout_<name>.json  +  _<name>_flat.png (flat silhouette review)  +  _<name>_stack.png

Usage:
  python gen_shape_layout.py --mask m.txt --name duck --layers 5 --target 180 [--out dir]
"""
import sys, os, json, argparse, struct, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from maskio import load_mask
import layout_builder as LB
from mask_to_layout import to_stones, center
from geom import (geom_symmetrize, geom_div3_trim, clean_div3_trim, d4_symmetrize, vh_symmetrize,
                  sym_scores, best_axis, auto_axis)
from gen_layouts import structural_ok, layout_diff, to_board
from tile_level_simulator import DifficultyScorer as DS
from render_png import layout_to_png


def _covered_above(c, cells):
    L, x, y = c
    return any(L2 > L and abs(x2 - x) < 1 and abs(y2 - y) < 1 for (L2, x2, y2) in cells)


def peel_to_target(cells, target, top_floor=3):
    """Remove EXPOSED top cells (nothing above -> removal never floats a supporter), farthest
    from centroid first, never touching layer 0, keeping >=top_floor cells in the top layer
    so the 5th layer survives. Lands exactly on `target` (must be reachable & %3==0)."""
    cells = [tuple(c) for c in cells]
    while len(cells) > target:
        cx = sum(c[1] for c in cells) / len(cells)
        cy = sum(c[2] for c in cells) / len(cells)
        topL = max(c[0] for c in cells)
        top_n = sum(1 for c in cells if c[0] == topL)
        exposed = [c for c in cells if c[0] >= 1 and not _covered_above(c, cells)]
        # protect the top layer from being peeled below the floor (keeps layer count)
        if top_n <= top_floor:
            exposed = [c for c in exposed if c[0] != topL]
        if not exposed:
            break
        victim = max(exposed, key=lambda c: (c[1] - cx) ** 2 + (c[2] - cy) ** 2)
        cells.remove(victim)
    return [list(c) for c in cells]


def peel_even(cells, target, top_floor=3):
    """EVEN depth: peel the TALLEST exposed cells first so tower heights level out and the
    hidden (upper) layers spread across the WHOLE silhouette instead of a central mound.
    Only removes exposed cells (never floats), never layer 0, keeps >=top_floor at the top
    layer so the 5th layer survives. Pair with a uniform_stagger build."""
    cells = [tuple(c) for c in cells]
    cx = sum(c[1] for c in cells) / len(cells)
    cy = sum(c[2] for c in cells) / len(cells)
    while len(cells) > target:
        topL = max(c[0] for c in cells)
        top_n = sum(1 for c in cells if c[0] == topL)
        exposed = [c for c in cells if c[0] >= 1 and not _covered_above(c, cells)]
        if top_n <= top_floor:                       # protect the 5th layer
            exposed = [c for c in exposed if c[0] != topL]
        if not exposed:
            break
        maxLe = max(c[0] for c in exposed)           # cap the tallest towers first -> even heights
        tall = [c for c in exposed if c[0] == maxLe]
        victim = max(tall, key=lambda c: (c[1] - cx) ** 2 + (c[2] - cy) ** 2)
        cells.remove(victim)
    return [list(c) for c in cells]


def render_flat(cells, out, ppu=24):
    """Flat single-colour base silhouette (L0) — the shape-fidelity review render."""
    l0 = [(x, y) for (L, x, y) in cells if L == 0]
    xs = [p[0] for p in l0]; ys = [p[1] for p in l0]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = ppu
    W = int(round((maxx - minx) * ppu)) + ppu + 2 * pad
    H = int(round((maxy - miny) * ppu)) + ppu + 2 * pad
    bg, fg = (245, 250, 253), (53, 187, 106)
    cv = [[bg for _ in range(W)] for _ in range(H)]
    side = ppu - 1
    for (x, y) in l0:
        px = int(round((x - minx) * ppu)) + pad
        py = int(round((maxy - y) * ppu)) + pad
        for yy in range(py, py + side):
            for xx in range(px, px + side):
                if 0 <= yy < H and 0 <= xx < W:
                    cv[yy][xx] = fg

    def ch(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(c for px in row for c in px) for row in cv)
    png = (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + ch(b"IDAT", zlib.compress(raw, 9)) + ch(b"IEND", b""))
    open(out, "wb").write(png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--layers", type=int, default=5)
    ap.add_argument("--target", type=int, default=0, help="exact total cells (%%3==0). 0 = natural")
    ap.add_argument("--mound", action="store_true",
                    help="concentrate hidden layers in a central MOUND (capped_inset). "
                         "DEFAULT is EVEN depth across the whole shape (uniform_stagger) — "
                         "user preference: prioritize even layers (raise --target if too shallow).")
    ap.add_argument("--mirror", dest="mirror", action="store_true", default=True,
                    help="PRIORITISE symmetry (DEFAULT ON): snap to the symmetry the shape supports. "
                         "Per-layer + coverage symmetry come for free (geometric cell-mirror keeps the "
                         "layer index). Symmetric layouts score 1.00 on their group's axes.")
    ap.add_argument("--no-mirror", dest="mirror", action="store_false",
                    help="do NOT force symmetry — for genuinely asymmetric/elongated shapes (sword, "
                         "key, arrow). Just measures & reports symmetry.")
    ap.add_argument("--axis", choices=["auto", "vertical", "horizontal", "vh", "d4"], default="auto",
                    help="auto (DEFAULT) = detect the shape's natural reflection axes and snap that "
                         "group (asymmetric shapes fall back to no-force); or force one: vertical=1 "
                         "axis L-R, horizontal=1 axis T-B, vh=2 axes, d4=4 axes (square/mandala).")
    ap.add_argument("--min-sym", type=float, default=0.0,
                    help="if >0, warn (exit 2) when the best of the 4 symmetry axes < this — lets "
                         "you re-trace or add --mirror. 0 = report only (never forces).")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    out_dir = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))), "layouts")
    os.makedirs(out_dir, exist_ok=True)

    even = not a.mound                                # DEFAULT: even layer distribution
    grid = load_mask(a.mask)
    # SIMPLIFY-FIRST budget: the board space is SMALL (real boards ~16-24 base footprints, ~6 layers,
    # mobile-portrait aspect ~0.88). A complex image must be SIMPLIFIED to fit — literal fidelity is
    # NOT the goal. Auto-run the complexity gate + warn when over budget so the user re-traces simpler.
    from maskio import count_on, dims as _dims
    on = count_on(grid); mh, mw = _dims(grid); asp = (mw / mh) if mh else 0.0
    try:
        import evaluate_icon as EI
        verdict, _m, reasons = EI.evaluate(grid)
        print(f"complexity: {verdict}  base_footprints={on}  aspect={asp:.2f}"
              + (f"  ({'; '.join(reasons)})" if reasons else ""))
        if verdict == "too-complex":
            print("  SIMPLIFY: too detailed for the board space — reduce to a lower-res silhouette "
                  "(fewer features) before building; don't chase literal fidelity.")
    except Exception as e:
        print(f"complexity gate skipped: {e}")
    if on > 48:
        print(f"  WARN: {on} base footprints > ~48 budget — likely too detailed; simplify the mask.")
    if asp > 1.10:
        print(f"  WARN: aspect {asp:.2f} > 1.10 — too wide for mobile-portrait; orient taller.")
    mode = "capped_inset" if a.mound else "uniform_stagger"
    cells = [[L, x, y] for (L, x, y) in LB.build(grid, mode=mode, max_layers=a.layers)]
    if not cells:
        raise SystemExit("ERROR: mask produced no cells (too small/thin). Use a larger/denser mask.")
    if a.target:
        if a.target % 3:
            raise SystemExit("target must be divisible by 3")
        cells = peel_to_target(cells, a.target) if a.mound else peel_even(cells, a.target)
    # Finalize to %3==0. SYMMETRY (B-audit fix): the old trim_to_mult3 dropped single off-axis cells
    # (V 1.0 -> 0.83) and the +0.5 stagger left even layers asymmetric (V~0.92) — both unfixed here
    # while compose was. --mirror snaps to exact symmetry (geom cell-mirror, drop mirror PAIRS);
    # default measures only (does not force), using the no-float exposed-top trim.
    # CENTER FIRST so the symmetry axis passes through 0 (build emits x=0..W, all positive).
    cells = center([list(c) for c in cells])
    tcells = [(c[0], c[1], c[2]) for c in cells]
    axis = a.axis; chosen_note = ""
    if a.mirror:
        if axis == "auto":                            # PRIORITISE symmetry: snap the group the shape supports
            axis = auto_axis(sym_scores(tcells))      # ('d4'/'vh'/'vertical'/'horizontal'/'none')
            chosen_note = f"  [auto:{axis}]"
        if axis == "d4":
            tcells = d4_symmetrize(tcells)            # all 4 reflection axes -> 1.00 (valid, div3)
        elif axis == "vh":
            tcells = vh_symmetrize(tcells)            # 2 orthogonal axes -> 1.00 (4 quadrants)
        elif axis in ("vertical", "horizontal"):
            tcells = geom_div3_trim(geom_symmetrize(tcells, axis=axis), axis=axis)
        else:                                         # "none" -> shape isn't symmetric; don't force
            tcells = clean_div3_trim(tcells)
            chosen_note = "  [auto:none — asymmetric, not forced]" if a.axis == "auto" else ""
    else:
        tcells = clean_div3_trim(tcells)
    cells = center([list(c) for c in tcells])

    ok = structural_ok([(c[0], c[1], c[2]) for c in cells])
    d = layout_diff(cells)
    nlay = max(c[0] for c in cells) + 1
    b = to_board([(c[0], c[1], c[2]) for c in cells])
    cov = DS.cover100_by_area(b, [id(c) for c in b.all_cells()], 0.9)
    scores = sym_scores([(c[0], c[1], c[2]) for c in cells])
    bax, bscore = best_axis([(c[0], c[1], c[2]) for c in cells])
    data = to_stones(cells, a.name)
    data["metadata"].update({"source": "shape_capped_inset" if a.mound else "shape_even",
                             "layout_difficulty": round(d, 2),
                             "cover100": cov, "cover100_ratio": round(cov / len(cells), 3),
                             "symmetry_axes": scores, "symmetry_best_axis": bax,
                             "symmetry_score": bscore})
    path = os.path.join(out_dir, f"NewLayout_{a.name}.json")
    json.dump(data, open(path, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    render_flat([(c[0], c[1], c[2]) for c in cells], os.path.join(out_dir, f"_{a.name}_flat.png"))
    layout_to_png(path, os.path.join(out_dir, f"_{a.name}_stack.png"), ppu=18)
    print(f"-> {path}")
    print(f"   total={len(cells)} layers={nlay} cover100={cov} ({cov/len(cells):.3f}) "
          f"diff={d:.2f} ok={ok}")
    sym_str = "  ".join(f"{k[:4]}={v:.2f}" for k, v in scores.items())
    print(f"   symmetry: {sym_str}  -> best {bax}={bscore:.2f}{chosen_note}")
    print(f"   flat review: _{a.name}_flat.png   stacked: _{a.name}_stack.png")
    if a.min_sym > 0 and bscore < a.min_sym:
        print(f"   WARNING: best symmetry {bscore:.2f} < --min-sym {a.min_sym:.2f} — "
              f"add --mirror or simplify/re-trace.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
