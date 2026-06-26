"""Add STRAIGHT-STACK columns to an EMPTY layout — a GEOMETRY step, run AFTER gen-layout but
BEFORE tile-level-design assigns tiles.

Why before tiles (user): a stack is a STRUCTURAL feature — a straight vertical pile (cells share the
exact (x,y) across layers, NO +0.5 stagger), so only the TOP is pickable and the lower cells are
fully covered. That changes pickability + cover100, which the v3 solver and the scorer must see when
tiles are assigned. So stacks belong to the layout geometry, not a post-tile overlay (mission/mark
cells, which only retype/flag existing tiles, are the post-tile step — see tile-level-design
add_special_cells.py).

Reverse-engineered format: a straight pile at (x,y) across layers 0..k, registered in the top-level
`stacks` list as {"x":x,"y":y,"d":d}. Created here by COLLAPSING a staggered tower onto its base
anchor (preserves cell count; re-validated structurally — a straight pile never floats).

Usage:
  python add_stacks.py <NewLayout.json> [--out out.json] [--seed 1] --n N [--depth D]
       # --n   number of towers to convert to straight stacks
       # --depth  the `d` value to record (omitted -> the tower's own height)
"""
import sys, os, json, argparse, random, math, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from gen_layouts import structural_ok, to_board
from tile_level_simulator import DifficultyScorer as DS
from geom import sym_scores, auto_axis


def cells_of(data):
    return [(ly["index"], float(s["x"]), float(s["y"])) for ly in data["layers"]
            for s in ly.get("stones", [])]


def towers(cells):
    col = {}
    for L, x, y in cells:
        anchor = (round(x - 0.5 * (L % 2)), round(y + 0.5 * (L % 2)))
        col.setdefault(anchor, []).append((L, x, y))
    return col


def _orbit(anchor, group):
    """Symmetry-group images of an anchor (so a placed stack set stays symmetric)."""
    x, y = anchor
    if group == "d4":
        return {(x, y), (-x, y), (x, -y), (-x, -y), (y, x), (-y, x), (y, -x), (-y, -x)}
    if group == "vh":
        return {(x, y), (-x, y), (x, -y), (-x, -y)}
    if group == "vertical":
        return {(x, y), (-x, y)}
    if group == "horizontal":
        return {(x, y), (x, -y)}
    return {(x, y)}


def _rank(anchor, pattern, rmax):
    """Lower = picked first. Patterns over the footprint (anchors are centred ~0)."""
    x, y = anchor; r = math.hypot(x, y)
    if pattern == "edge":                      # outermost ring first (frame look, like real L117)
        return (-max(abs(x), abs(y)), -r)
    if pattern == "corners":                   # extreme diagonal corners first
        return (-(x * x + y * y), abs(abs(x) - abs(y)))
    if pattern == "ring":                      # a mid radius
        return (abs(r - rmax * 0.55), r)
    return (r,)                                # 'center' fallback


def to_stones_keep(data, cells):
    """Rewrite data['layers'] from cells [(L,x,y)] (empty layout — no tile ids)."""
    by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append({"x": round(x, 2), "y": round(y, 2)})
    data["layers"] = [{"index": L, "stones": by[L]} for L in sorted(by)]
    return data


def _apply_group(cells, group):
    """Re-impose the layout's reflection group on the cells (restores EXACT symmetry after a collapse,
    equalising mirror-stack heights via orbit-union). Straight cells reflect to straight cells, so the
    stacks survive."""
    from geom import geom_symmetrize, geom_div3_trim, vh_symmetrize, d4_symmetrize
    if group == "none":
        return cells
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2; cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    c0 = [(int(L), round(x - cx, 2), round(y - cy, 2)) for L, x, y in cells]
    if group == "d4":
        c1 = d4_symmetrize(c0)
    elif group == "vh":
        c1 = vh_symmetrize(c0)
    else:
        c1 = geom_div3_trim(geom_symmetrize(c0, axis=group), axis=group)
    return [(int(L), round(x + cx, 2), round(y + cy, 2)) for L, x, y in c1]


def add_stacks(cells, stacks_field, n, depth, pattern, rng):
    """Place ~n straight stacks by PATTERN (edge/ring/corners) and keep the layout EXACTLY symmetric:
    pick seed towers by pattern, expand each to its full mirror ORBIT (so positions are symmetric),
    collapse those towers to straight piles, then RE-IMPOSE the symmetry group (which equalises the
    mirror stacks' heights — the +0.5 stagger makes a tower and its mirror group to different anchor
    heights, so a raw collapse alone would read ~0.93, not 1.00)."""
    col = towers(cells)
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2; cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    cc = [(L, round(x - cx, 2), round(y - cy, 2)) for L, x, y in cells]
    group = auto_axis(sym_scores(cc), thr=0.9)          # 'd4'/'vh'/'vertical'/'horizontal'/'none'
    acx, acy = round(cx), round(cy)
    cand = {}                                           # centred anchor -> (raw anchor, tower cells)
    for (ax, ay), tc in col.items():
        if len(tc) >= 2:
            cand[(ax - acx, ay - acy)] = ((ax, ay), tc)
    rmax = max((math.hypot(a[0], a[1]) for a in cand), default=1.0)
    seeds = sorted(cand, key=lambda a: (_rank(a, pattern, rmax), rng.random()))
    chosen = set(); picked = set()                      # raw anchors to straighten
    for ca in seeds:
        if len(chosen) >= n:
            break
        orbit = _orbit(ca, group)
        if not all(o in cand for o in orbit) or any(o in picked for o in orbit):
            continue                                    # incomplete/overlapping orbit -> skip (stays symmetric)
        for o in orbit:
            picked.add(o); chosen.add(cand[o][0])
    # collapse chosen towers onto their anchors (straight pile), keep others as-is
    out = []
    for (ax, ay), tc in col.items():
        if (ax, ay) in chosen:
            out.extend((L, float(ax), float(ay)) for (L, _x, _y) in tc)
        else:
            out.extend(tc)
    out = _apply_group(out, group)                      # restore EXACT symmetry (equalise stack heights)
    # register the stacks field: chosen positions that now hold a straight column (>=2 cells same x,y)
    posc = collections.Counter((round(x, 2), round(y, 2)) for _L, x, y in out)
    occupied = {(round(e["x"], 2), round(e["y"], 2)) for e in stacks_field}
    made = []
    for (ax, ay) in sorted(chosen):
        key = (float(ax), float(ay)); cnt = posc.get(key, 0)
        if cnt >= 2 and key not in occupied:
            stacks_field.append({"x": float(ax), "y": float(ay), "d": int(depth or cnt)})
            occupied.add(key); made.append(((ax, ay), cnt))
    return out, made, group


def main():
    ap = argparse.ArgumentParser(description="Add straight-stack columns to an empty layout (pre-tile).")
    ap.add_argument("layout")
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--n", type=int, required=True, help="target number of straight stacks (rounds up to symmetric orbits)")
    ap.add_argument("--depth", type=int, default=0, help="0 = record each tower's own height as d")
    ap.add_argument("--pattern", choices=["edge", "ring", "corners"], default="edge",
                    help="placement pattern over the footprint (default edge = outer frame, like real Mission)")
    a = ap.parse_args()

    data = json.load(open(a.layout, encoding="utf-8"))
    data.setdefault("stacks", [])
    cells = cells_of(data)
    new_cells, made, group = add_stacks(cells, data["stacks"], a.n, a.depth, a.pattern, random.Random(a.seed))

    ct = [(int(L), x, y) for L, x, y in new_cells]
    ok = structural_ok(ct)
    if not ok:
        print("WARNING: structural_ok=False after stacking — a collapse collided; reduce --n or reseed.")
    to_stones_keep(data, new_cells)
    b = to_board(ct)
    cov = DS.cover100_by_area(b, [id(c) for c in b.all_cells()], 0.9)

    out = a.out or a.layout.replace(".json", "_stacks.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}")
    print(f"   straight stacks: +{len(made)} (pattern={a.pattern}, symmetry={group}) "
          f"{[f'{a_}x{h}' for a_, h in made]}  structural_ok={ok}")
    print(f"   cover100={cov} ({cov/len(ct):.2f}) — straight piles fully cover their lower cells "
          f"(only the top is pickable). Now hand to tile-level-design to assign tiles + solve.")


if __name__ == "__main__":
    main()
