"""Fully-symmetric bulk layout generator via SYMMETRIC-COMPONENT crossover.

Why: empirical_gen samples+perturbs a real board but its top-trim + support-cleanup break exact
symmetry -> "gần đối xứng". This module guarantees EXACT h-symmetry BY CONSTRUCTION and stays
novel (not in the competitor pool) by recombining symmetric half-clusters mined from the real
symmetric boards.

KEY (per design review): symmetry is defined at the TOWER / base-anchor level, NOT geometric
cell-mirror. A tower = base anchor (bx,by) + set of layers present. The +0.5 odd-layer stagger
leans the SAME way on both sides (game convention); a raw geometric mirror of a +0.5 cell would
land at -0.5 and break the stagger. So we mirror base anchors and re-render the stagger.

Pipeline:
  mine: exact-symmetric real boards -> connected half-clusters (side) + centred clusters (center)
  compose: take a real exact-sym skeleton -> swap 1-2 side half-clusters for mined donors at the
           same slot -> mirror -> render. Gates: in_envelope + assert sym_h==1.0 + dedup.
"""
import os, sys, json, zipfile, random, hashlib, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from empirical_gen import _in_envelope
from mask_to_layout import to_stones
from gen_layouts import structural_ok, layout_diff

SKILL_ROOT = os.path.dirname(HERE)
ZIP = os.path.join(SKILL_ROOT, "refs", "boards_Full.zip")
if not os.path.exists(ZIP):
    ZIP = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(SKILL_ROOT))), "refs", "boards_Full.zip")


# ---------- tower-level core ----------
def extract_towers(cells):
    """cells [(L,x,y)] -> {(bx,by): frozenset(layers)}. Undo the +0.5 stagger to the base anchor."""
    tw = {}
    for L, x, y in cells:
        bx = round(x - 0.5 * (L % 2)); by = round(y + 0.5 * (L % 2))
        tw.setdefault((bx, by), set()).add(int(L))
    return {k: frozenset(v) for k, v in tw.items()}


def render_towers(tw):
    """{(bx,by): layers} -> cells [(L,x,y)] with the game stagger re-applied."""
    cells = []
    for (bx, by), layers in tw.items():
        for L in layers:
            s = 0.5 if (L % 2) else 0.0
            cells.append((L, round(bx + s, 2), round(by - s, 2)))
    return cells


def axis_center(tw):
    """Translate so the h-symmetry axis sits at integer x=0 (and y min-anchored)."""
    xs = [k[0] for k in tw]; ys = [k[1] for k in tw]
    cx = round((min(xs) + max(xs)) / 2)
    return {(bx - cx, by): L for (bx, by), L in tw.items()}


def mirror_towers(tw):
    return {(-bx, by): L for (bx, by), L in tw.items()}


def sym_h(tw):
    """fraction of towers whose mirror partner exists with the SAME layer-set (axis x=0)."""
    if not tw:
        return 0.0
    return sum(1 for (bx, by), L in tw.items() if tw.get((-bx, by)) == L) / len(tw)


def is_exact_sym(tw):
    return sym_h(tw) == 1.0


def clusters(tw, conn8=True):
    """connected groups of base anchors (8-connected). Returns list of dict {(bx,by):layers}."""
    nbrs = [(-1, 0), (1, 0), (0, -1), (0, 1)] + ([(-1, -1), (-1, 1), (1, -1), (1, 1)] if conn8 else [])
    seen = set(); out = []
    for start in tw:
        if start in seen:
            continue
        stack = [start]; seen.add(start); grp = {}
        while stack:
            k = stack.pop(); grp[k] = tw[k]
            for dx, dy in nbrs:
                n = (k[0] + dx, k[1] + dy)
                if n in tw and n not in seen:
                    seen.add(n); stack.append(n)
        out.append(grp)
    return out


def _bbox(grp):
    xs = [k[0] for k in grp]; ys = [k[1] for k in grp]
    return min(xs), min(ys), max(xs), max(ys)


def sig_hash(cells):
    key = sorted((L, round(x, 1), round(y, 1)) for L, x, y in cells)
    return hashlib.md5(str(key).encode()).hexdigest()


# ---------- load boards ----------
def _load_cells(d):
    cs = []
    for ly in d.get("layers", []):
        L = ly.get("index", ly.get("layer", 0))
        for s in ly.get("stones", ly.get("cells", [])):
            try:
                cs.append((int(L), float(s["x"]), float(s["y"])))
            except Exception:
                pass
    return cs


def iter_exact_sym_boards(limit=None):
    """Yield axis-centred tower-dicts for boards that are (force-)exactly symmetric."""
    z = zipfile.ZipFile(ZIP)
    names = [n for n in z.namelist() if n.endswith(".json")]
    n = 0
    for nm in names:
        try:
            cells = _load_cells(json.loads(z.read(nm)))
        except Exception:
            continue
        if len(cells) < 6:
            continue
        tw = axis_center(extract_towers(cells))
        if sym_h(tw) >= 0.9:
            # force exact: union with mirror (add missing mirror partners w/ same layer-set)
            ftw = dict(tw)
            for (bx, by), L in tw.items():
                ftw.setdefault((-bx, by), L)
                ftw[(-bx, by)] = ftw[(-bx, by)] | L
                ftw[(bx, by)] = ftw[(bx, by)] | L
            # make both sides identical layer-sets
            ftw = {k: (ftw[k] | ftw.get((-k[0], k[1]), frozenset())) for k in ftw}
            if is_exact_sym(ftw):
                yield ftw
                n += 1
                if limit and n >= limit:
                    return


# ---------- mine component bank (cached to a bundled JSON for offline use) ----------
CACHE = os.path.join(SKILL_ROOT, "symmetric_components.json")


def _grp_to_json(grp):
    return [[bx, by, sorted(L)] for (bx, by), L in grp.items()]


def _grp_from_json(lst):
    return {(bx, by): frozenset(ls) for bx, by, ls in lst}


def _mine_from_zip(limit=None):
    side, center, skeletons = [], [], []
    for tw in iter_exact_sym_boards(limit):
        skeletons.append(tw)
        for grp in clusters(tw):
            if {(-bx, by) for (bx, by) in grp} == set(grp):     # centred component
                center.append(grp)
            else:
                x0, y0, x1, y1 = _bbox(grp)
                if x0 > 0:                                      # +x representative
                    norm = {(bx - x0, by - y0): L for (bx, by), L in grp.items()}
                    side.append({"cells": norm, "w": x1 - x0, "h": y1 - y0, "n": len(grp)})
    return {"side": side, "center": center, "skeletons": skeletons}


def build_cache(limit=None):
    bank = _mine_from_zip(limit)
    ser = {"side": [{"cells": _grp_to_json(d["cells"]), "w": d["w"], "h": d["h"], "n": d["n"]} for d in bank["side"]],
           "center": [_grp_to_json(g) for g in bank["center"]],
           "skeletons": [_grp_to_json(g) for g in bank["skeletons"]]}
    json.dump(ser, open(CACHE, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"cached bank -> {CACHE}  side={len(ser['side'])} center={len(ser['center'])} skeletons={len(ser['skeletons'])}")
    return bank


def mine_bank(limit=None):
    """Load the bundled component cache if present (offline-safe); else mine from boards_Full.zip."""
    if os.path.exists(CACHE):
        ser = json.load(open(CACHE, encoding="utf-8"))
        return {"side": [{"cells": _grp_from_json(d["cells"]), "w": d["w"], "h": d["h"], "n": d["n"]} for d in ser["side"]],
                "center": [_grp_from_json(g) for g in ser["center"]],
                "skeletons": [_grp_from_json(g) for g in ser["skeletons"]]}
    return _mine_from_zip(limit)


# ---------- GEOMETRIC cell-mirror symmetry (matches real boards: odd cells flip lean) ----------
# Measured on 213 real exact-tower-sym boards: geometric cell-mirror sym median=1.00. So the game
# renders symmetric boards cell-mirrored (odd +0.5 cell on the left has its mirror at -0.5 on the
# right), NOT tower-mirrored (same lean both sides). Tower-mirror leaves a visible "missing cell".
def geom_symmetrize(cells):
    """Keep the x>0 half + axis(x==0) cells, add geometric mirrors (L,-x,y). Axis at x=0."""
    dom = set(); axis = set()
    for (L, x, y) in cells:
        x = round(x, 2); y = round(y, 2)
        if x > 0.01:
            dom.add((L, x, y))
        elif abs(x) <= 0.01:
            axis.add((L, x, y))
    full = set(axis) | dom | {(L, round(-x, 2), y) for (L, x, y) in dom}
    return [(L, x, y) for (L, x, y) in full]


def is_geom_sym(cells):
    s = set((L, round(x, 2), round(y, 2)) for L, x, y in cells)
    return all((L, round(-x, 2), round(y, 2)) in s for (L, x, y) in s)


def _exposed_top(cells):
    """cells with no higher-layer cell overlapping (a removable top, never floats anything)."""
    s = list(cells)
    out = []
    for (L, x, y) in s:
        if not any(L2 > L and abs(x2 - x) < 1 and abs(y2 - y) < 1 for (L2, x2, y2) in s):
            out.append((L, x, y))
    return out


def geom_div3_trim(cells):
    """Trim to %3==0 while KEEPING geometric symmetry: drop mirror PAIRS of exposed tops (2),
    or one axis (x==0) exposed top for the %3==1 case. Removes only exposed cells (no floating)."""
    s = set((L, round(x, 2), round(y, 2)) for L, x, y in cells)
    guard = 0
    while len(s) % 3 and guard < 300:
        guard += 1
        tops = _exposed_top(s)
        axis_tops = [c for c in tops if abs(c[1]) <= 0.01 and c[0] > 0]   # keep base layer
        side_tops = [c for c in tops if c[1] > 0.01 and c[0] > 0]
        if len(s) % 3 == 1 and axis_tops:
            c = max(axis_tops, key=lambda c: c[0]); s.discard(c)
        elif side_tops:
            c = max(side_tops, key=lambda c: (c[1] ** 2 + c[2] ** 2))
            mc = (c[0], round(-c[1], 2), c[2])
            s.discard(c); s.discard(mc)
        elif axis_tops:
            c = max(axis_tops, key=lambda c: c[0]); s.discard(c)
        else:
            break
    return [(L, x, y) for (L, x, y) in s]


# ---------- symmetric div3 trim (preserves exact symmetry) ----------
def sym_div3_trim(tw):
    tw = {k: set(v) for k, v in tw.items()}
    total = sum(len(v) for v in tw.values())
    guard = 0
    while total % 3 and guard < 300:
        guard += 1
        center = [k for k in tw if k[0] == 0 and len(tw[k]) > 1]
        side = [k for k in tw if k[0] > 0 and len(tw[k]) > 1 and (-k[0], k[1]) in tw]
        if total % 3 == 1 and center:                    # remove 1 cell from a centre tower top
            k = max(center, key=lambda k: max(tw[k])); tw[k].discard(max(tw[k])); total -= 1
        elif side:                                       # remove a mirror PAIR top (2 cells)
            k = max(side, key=lambda k: (k[0] ** 2 + k[1] ** 2)); mk = (-k[0], k[1])
            tw[k].discard(max(tw[k])); tw[mk].discard(max(tw[mk])); total -= 2
        elif center:                                     # fallback: 2 centre trims
            k = max(center, key=lambda k: max(tw[k])); tw[k].discard(max(tw[k])); total -= 1
        else:
            break
    return {k: frozenset(v) for k, v in tw.items() if v}


# ---------- compose via cluster crossover ----------
def compose_crossover(rng, bank, n_swaps=1):
    """Take a real exact-sym skeleton, swap n_swaps +x half-clusters for mined donors at the same
    slot, mirror, render. Returns cells or None (rejected -> caller resamples)."""
    skel = rng.choice(bank["skeletons"])
    cl = clusters(skel)
    centers = [g for g in cl if {(-bx, by) for (bx, by) in g} == set(g)]
    sides = []                                            # +x representatives (one per mirror pair)
    for g in cl:
        if {(-bx, by) for (bx, by) in g} == set(g):
            continue
        x0, _, _, _ = _bbox(g)
        if x0 > 0:
            sides.append(g)
    if not sides:
        return None
    n_swaps = min(n_swaps, len(sides))
    swap_idx = set(rng.sample(range(len(sides)), n_swaps))

    placed = {}                                           # rebuild +x side + centres, then mirror
    def put(grp):
        for k, L in grp.items():
            if k in placed:
                return False                              # tower collision -> reject
            placed[k] = L
        return True

    for g in centers:
        if not put(g):
            return None
    for i, g in enumerate(sides):
        if i in swap_idx:
            x0, y0, x1, y1 = _bbox(g)
            cand = [d for d in bank["side"] if abs(d["w"] - (x1 - x0)) <= 1 and abs(d["h"] - (y1 - y0)) <= 1]
            if not cand:
                cand = bank["side"]
            d = rng.choice(cand)
            donor = {(bx + x0, by + y0): L for (bx, by), L in d["cells"].items()}  # anchor to slot
            if min(k[0] for k in donor) < 1:              # must stay strictly off-axis
                return None
            if not put(donor):
                return None
        else:
            if not put(g):
                return None
    # render the +x-and-centre half, then GEOMETRIC cell-mirror (matches real boards — see above).
    # axis_center puts the symmetry axis at x=0; the half is rendered with the normal +0.5 stagger,
    # and geom_symmetrize reflects x>0 -> x<0 so odd cells flip lean (true visual symmetry).
    half_cells = render_towers(axis_center(placed))
    cells = geom_symmetrize(half_cells)
    cells = geom_div3_trim(cells)
    ct = [(int(L), round(x, 2), round(y, 2)) for (L, x, y) in cells]
    if len(ct) < 12 or len(ct) % 3:
        return None
    if not is_geom_sym(ct) or not structural_ok(ct) or not _in_envelope(ct):
        return None
    xs = [c[1] for c in ct]; ys = [c[2] for c in ct]
    cy = round((min(ys) + max(ys)) / 2 * 2) / 2          # keep axis at x=0; only re-centre y
    return [(L, x, round(y - cy, 2)) for (L, x, y) in ct]


def geom_sym_frac(cells):
    """fraction of cells whose geometric mirror (L,-x,y) also exists (axis x=0)."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    return sum(1 for (L, x, y) in s if (L, round(-x, 2), y) in s) / len(s) if s else 0.0


def _clean_div3_trim_cells(cells):
    """Trim to %3==0 by removing EXPOSED tops only (no floating), highest+farthest first.
    No symmetry constraint -> used for the intentionally-asymmetric path."""
    s = set((int(L), round(x, 2), round(y, 2)) for L, x, y in cells)
    guard = 0
    while len(s) % 3 and guard < 300:
        guard += 1
        tops = _exposed_top(s)
        if not tops:
            break
        s.discard(max(tops, key=lambda c: (c[0], c[1] ** 2 + c[2] ** 2)))
    return [(L, x, y) for (L, x, y) in s]


def compose_asym_clean(rng, bank, n_swaps=1):
    """CLEAN natural asymmetry: build a symmetric crossover board at the TOWER level, then drop
    ONE whole side-cluster on a SINGLE side (keep its mirror). Result reads symmetric except one
    feature -> like real near-symmetric boards. No per-tower random trim => no jaggedness.
    Returns cells or None (rejected -> caller resamples)."""
    skel = rng.choice(bank["skeletons"])
    cl = clusters(skel)
    centers = [g for g in cl if {(-bx, by) for (bx, by) in g} == set(g)]
    sides = []
    for g in cl:
        if {(-bx, by) for (bx, by) in g} == set(g):
            continue
        x0, _, _, _ = _bbox(g)
        if x0 > 0:
            sides.append(g)
    if not sides:
        return None
    swap_idx = set(rng.sample(range(len(sides)), min(n_swaps, len(sides))))
    placed = {}
    def put(grp):
        for k, L in grp.items():
            if k in placed:
                return False
            placed[k] = L
        return True
    for g in centers:
        if not put(g):
            return None
    chosen_sides = []
    for i, g in enumerate(sides):
        if i in swap_idx:
            x0, y0, x1, y1 = _bbox(g)
            cand = [d for d in bank["side"] if abs(d["w"] - (x1 - x0)) <= 1 and abs(d["h"] - (y1 - y0)) <= 1] or bank["side"]
            d = rng.choice(cand)
            donor = {(bx + x0, by + y0): L for (bx, by), L in d["cells"].items()}
            if min(k[0] for k in donor) < 1 or not put(donor):
                return None
            chosen_sides.append(donor)
        else:
            if not put(g):
                return None
            chosen_sides.append(g)
    # full symmetric tower set, then break symmetry by removing one side-cluster on one side
    full = dict(placed)
    for (bx, by), L in placed.items():
        if bx > 0:
            full[(-bx, by)] = L
    drop = rng.choice(chosen_sides)
    side_sign = rng.choice([1, -1])
    for (bx, by) in drop:
        full.pop((side_sign * bx, by), None)
    if len(full) < 4:
        return None
    full = axis_center(full)
    cells = _clean_div3_trim_cells(render_towers(full))
    ct = [(int(L), round(x, 2), round(y, 2)) for (L, x, y) in cells]
    if len(ct) < 12 or len(ct) % 3:
        return None
    if not structural_ok(ct) or not _in_envelope(ct):
        return None
    xs = [c[1] for c in ct]; ys = [c[2] for c in ct]
    cx = round((min(xs) + max(xs)) / 2 * 2) / 2; cy = round((min(ys) + max(ys)) / 2 * 2) / 2
    return [(L, round(x - cx, 2), round(y - cy, 2)) for (L, x, y) in ct]


def generate_mixed(n, out_dir, seed=1, sym_frac=0.64, bank_limit=None):
    """Distribution-correct bulk: ~sym_frac exact-symmetric + the rest clean-asymmetric.
    Matches the real ~64% h-symmetric mix WITHOUT the empirical-mode jaggedness."""
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(seed)
    print("mining symmetric component bank from real boards...", flush=True)
    bank = mine_bank(limit=bank_limit)
    print(f"  bank: side={len(bank['side'])} center={len(bank['center'])} skeletons={len(bank['skeletons'])}")
    excl = set()
    sp = os.path.join(SKILL_ROOT, "excluded_sigs.json")
    if os.path.exists(sp):
        excl = set(json.load(open(sp, encoding="utf-8")))
    n_sym = round(n * sym_frac); n_asym = n - n_sym
    seen = set(); kept = []; attempts = 0; rej = {"build": 0, "dup": 0}
    made_sym = made_asym = 0
    while (made_sym < n_sym or made_asym < n_asym) and attempts < n * 120:
        attempts += 1
        if made_sym >= n_sym:
            do_sym = False
        elif made_asym >= n_asym:
            do_sym = True
        else:
            do_sym = rng.random() < sym_frac
        cells = (compose_crossover if do_sym else compose_asym_clean)(rng, bank, n_swaps=rng.choice([1, 1, 2]))
        if not cells:
            rej["build"] += 1; continue
        h = sig_hash(cells)
        if h in excl or h in seen:
            rej["dup"] += 1; continue
        seen.add(h)
        idx = len(kept) + 1; name = f"mix_{idx:04d}"
        data = to_stones([list(c) for c in cells], name)
        d = layout_diff(cells)
        data["metadata"].update({"source": "mixed_bulk", "layout_difficulty": round(d, 2),
                                 "symmetry": "geometric_h" if do_sym else "asymmetric",
                                 "sym_h": 1.0 if do_sym else round(geom_sym_frac(cells), 2)})
        json.dump(data, open(os.path.join(out_dir, f"NewLayout_{name}.json"), "w", encoding="utf-8"),
                  separators=(",", ":"), ensure_ascii=False)
        kept.append({"name": name, "kind": "sym" if do_sym else "asym", "cells": len(cells),
                     "n_layers": max(c[0] for c in cells) + 1, "layout_difficulty": round(d, 2),
                     "sym_h": 1.0 if do_sym else round(geom_sym_frac(cells), 2)})
        if do_sym:
            made_sym += 1
        else:
            made_asym += 1
    json.dump({"produced": len(kept), "attempts": attempts, "reject": rej,
               "n_sym": made_sym, "n_asym": made_asym, "sym_frac_target": sym_frac, "layouts": kept},
              open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"PRODUCED {len(kept)}/{n} in {attempts} attempts -> {out_dir}  reject={rej}")
    print(f"  sym={made_sym} asym={made_asym}  (target sym_frac={sym_frac})")
    if kept:
        df = [k["layout_difficulty"] for k in kept]
        print(f"  cells {min(k['cells'] for k in kept)}..{max(k['cells'] for k in kept)}  diff {min(df):.1f}..{max(df):.1f}")


def generate(n, out_dir, seed=1, n_swaps=1, bank_limit=None):
    os.makedirs(out_dir, exist_ok=True)
    rng = random.Random(seed)
    print(f"mining symmetric component bank from real boards...", flush=True)
    bank = mine_bank(limit=bank_limit)
    print(f"  bank: side={len(bank['side'])} center={len(bank['center'])} skeletons={len(bank['skeletons'])}")
    # exclusion = competitor pool signatures (bundled) + generated
    excl = set()
    sp = os.path.join(SKILL_ROOT, "excluded_sigs.json")
    if os.path.exists(sp):
        excl = set(json.load(open(sp, encoding="utf-8")))
    seen = set(); kept = []; attempts = 0; rej = {"build": 0, "dup": 0}
    while len(kept) < n and attempts < n * 80:
        attempts += 1
        cells = compose_crossover(rng, bank, n_swaps=rng.choice([1, 1, 2]))
        if not cells:
            rej["build"] += 1; continue
        h = sig_hash(cells)
        if h in excl or h in seen:
            rej["dup"] += 1; continue
        seen.add(h)
        idx = len(kept) + 1
        name = f"sym_{idx:04d}"
        data = to_stones([list(c) for c in cells], name)
        d = layout_diff(cells)
        data["metadata"].update({"source": "symmetric_crossover", "layout_difficulty": round(d, 2),
                                 "symmetry": "geometric_h", "sym_h": 1.0})
        json.dump(data, open(os.path.join(out_dir, f"NewLayout_{name}.json"), "w", encoding="utf-8"),
                  separators=(",", ":"), ensure_ascii=False)
        kept.append({"name": name, "cells": len(cells), "n_layers": max(c[0] for c in cells) + 1,
                     "layout_difficulty": round(d, 2)})
    json.dump({"produced": len(kept), "attempts": attempts, "reject": rej, "layouts": kept},
              open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print(f"PRODUCED {len(kept)}/{n} in {attempts} attempts -> {out_dir}  reject={rej}")
    if kept:
        df = [k["layout_difficulty"] for k in kept]
        print(f"  cells {min(k['cells'] for k in kept)}..{max(k['cells'] for k in kept)}  "
              f"diff {min(df):.1f}..{max(df):.1f}  ALL sym_h=1.0")


# ---------- self-test: lock the symmetry definition ----------
def selftest():
    print("ZIP:", ZIP, "exists:", os.path.exists(ZIP))
    tw = next(iter_exact_sym_boards(limit=1))
    cells = render_towers(tw)
    tw2 = axis_center(extract_towers(cells))
    print("round-trip sym_h:", sym_h(tw2), "(want 1.0)")
    # mirror via base anchors then re-render -> must stay exact-sym
    mt = {**tw, **mirror_towers(tw)}
    print("mirror+render exact-sym:", is_exact_sym(axis_center(extract_towers(render_towers(mt)))))
    bank = mine_bank(limit=200)
    print(f"bank from 200 boards: side={len(bank['side'])} center={len(bank['center'])} "
          f"skeletons={len(bank['skeletons'])}")
    # cluster count sanity
    import statistics as st
    cc = [len(clusters(s)) for s in bank["skeletons"]]
    print("clusters/board median:", st.median(cc))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--out", default="")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bank-limit", type=int, default=0, help="cap source boards (0=all exact-sym)")
    ap.add_argument("--build-cache", action="store_true", help="mine boards_Full.zip -> bundled symmetric_components.json")
    a = ap.parse_args()
    if a.build_cache:
        build_cache(a.bank_limit or None)
    if a.selftest:
        selftest()
    if a.n:
        generate(a.n, a.out or os.path.join(os.getcwd(), "layouts", "sym_pool"),
                 seed=a.seed, bank_limit=a.bank_limit or None)
