"""UC5 — clone a reference Tile Explorer layout's style into a NEW empty layout.

Reads an external board JSON (Oakever boards_Full format OR our NewLayout format),
extracts a SIGNATURE (layers, cells, footprint, coverage, symmetry, layout-difficulty),
then generates a clone: takes the reference BASE footprint, optionally varies it
(mirror/rotate so it is not a byte copy), rebuilds stacked, and honours user overrides
(--layers, --tiles). Reports reference-vs-clone signature.

Usage:
  python clone_layout.py --ref board_0000.json --out ../../../layouts/NewLayout_clone.json
  python clone_layout.py --ref board_0000.json --layers 4 --tiles 120 --vary mirror_h --out ...
"""
import sys, os, json, argparse, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import shape_factory as SF
import layout_builder as LB
from mask_to_layout import trim_to_mult3, center, to_stones
import fit_layout as FL
import gen_layouts as GL
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer


def load_board(path):
    """Return cells [(layer, x, y)] from external board OR our NewLayout format."""
    d = json.load(open(path, encoding="utf-8"))
    cells = []
    if "layers" in d and d["layers"] and "cells" in d["layers"][0]:      # external boards_Full
        for ly in d["layers"]:
            L = ly["layer"]
            for c in ly["cells"]:
                cells.append((L, float(c["x"]), float(c["y"])))
    elif "layers" in d:                                                   # our NewLayout (stones)
        for ly in d["layers"]:
            L = ly["index"]
            for s in ly["stones"]:
                cells.append((L, float(s["x"]), float(s["y"])))
    else:
        raise SystemExit("unknown board format")
    return cells


def base_grid(cells):
    """Layer-0 footprint -> 0/1 grid (row 0 = top). Layer-0 coords are integers."""
    base = [(x, y) for (L, x, y) in cells if L == 0]
    xs = [x for x, y in base]; ys = [y for x, y in base]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w = int(round(maxx - minx)) + 1; h = int(round(maxy - miny)) + 1
    g = [[0] * w for _ in range(h)]
    for x, y in base:
        c = int(round(x - minx)); r = int(round(maxy - y))   # flip y so row 0 = top
        g[r][c] = 1
    return g


def signature(cells):
    by = {}
    for L, x, y in cells: by.setdefault(L, []).append((x, y))
    xs = [x for _, x, y in cells]; ys = [y for _, x, y in cells]
    b = Board("s");
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = -1; ly.cells.append(cc)
        b.layers.append(ly)
    diff = DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))
    g = base_grid(cells)
    sym_h = g == SF.mirror_h(g); sym_v = g == SF.mirror_v(g)
    return {
        "n_layers": len(by), "cell_count": len(cells), "capacity": len(cells) // 3,
        "cells_per_layer": {L: len(by[L]) for L in sorted(by)},
        "footprint_wh": [int(round(max(xs) - min(xs))) + 1, int(round(max(ys) - min(ys))) + 1],
        "layout_difficulty": round(diff, 2),
        "coverage_hist": LB.coverage_histogram(cells),
        "symmetry": {"h": sym_h, "v": sym_v},
    }


def _isometry(cells, vary):
    """Mirror/rotate the WHOLE stack in world coords — preserves cover geometry, stagger,
    and therefore difficulty/coverage exactly. Gives a distinct-but-faithful clone."""
    out = []
    for (L, x, y) in cells:
        if vary == "mirror_h": x = -x
        elif vary == "mirror_v": y = -y
        elif vary == "rot90": x, y = -y, x
        out.append([L, x, y])
    return out


def clone(cells, layers=None, tiles=None, vary="none"):
    # FAITHFUL path: no depth change -> reproduce the reference's full multi-layer
    # structure (optionally mirrored/rotated). Difficulty + coverage match the ref.
    if layers is None and vary in ("none", "mirror_h", "mirror_v", "rot90"):
        built = _isometry(cells, vary)
        if tiles:                                # honour a tile-count note by trimming down
            N = tiles - (tiles % 3)
            while len(built) > N:
                top = max(c[0] for c in built); tops = [c for c in built if c[0] == top]
                if len(tops) <= 1: break
                built.remove(max(tops, key=lambda c: c[1] ** 2 + c[2] ** 2))
        built, _ = trim_to_mult3(built)
        return center(built)
    # REBUILD path: user changed the depth (--layers) or asked for jitter -> rebuild from
    # the base footprint with uniform_stagger. Geometry/difficulty WILL diverge from the ref
    # (expected — the user is deliberately restructuring it).
    g = base_grid(cells)
    g = SF.apply_transform(g, vary, __import__("random").Random(7)) if vary not in ("none",) else g
    L = layers or len({L for L, _, _ in cells})
    built = [[a, b, c] for (a, b, c) in LB.build(g, mode="uniform_stagger", max_layers=L)]
    if tiles:
        N = tiles - (tiles % 3)
        built = [list(c) for c in FL.trim_to([(c[0], c[1], c[2]) for c in built], N)]
    built, _ = trim_to_mult3(built)
    return center(built)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out")
    ap.add_argument("--layers", type=int)
    ap.add_argument("--tiles", type=int)
    ap.add_argument("--vary", default="none", choices=["none", "mirror_h", "mirror_v", "rot90", "jitter_edge"])
    a = ap.parse_args()

    ref = load_board(a.ref)
    sig_ref = signature(ref)
    cells = clone(ref, a.layers, a.tiles, a.vary)
    ct = [(c[0], c[1], c[2]) for c in cells]
    sig_clone = signature(ct)
    structural = GL.structural_ok(ct)

    print(f"REF   {os.path.basename(a.ref)}: {sig_ref}")
    print(f"CLONE (layers={a.layers or 'ref'} tiles={a.tiles or 'ref-match'} vary={a.vary}): {sig_clone}")
    print(f"structural_ok={structural}")
    if a.out:
        name = os.path.basename(a.out).replace("NewLayout_", "").replace(".json", "")
        data = to_stones([list(c) for c in cells], name)
        data["metadata"]["cloned_from"] = os.path.basename(a.ref)
        data["metadata"]["ref_signature"] = sig_ref
        data["metadata"]["layout_difficulty"] = sig_clone["layout_difficulty"]
        json.dump(data, open(a.out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
        print(f"SAVED {a.out}")


if __name__ == "__main__":
    main()
