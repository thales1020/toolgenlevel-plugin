"""RIGOROUS validation of the prior/generator (classifier-free, held-out, falsifiable).

Pipeline:
  1. DEDUP the corpus (exact-signature) -> distinct boards only.
  2. SPLIT distinct -> TRAIN / TEST (held-out; never used to calibrate).
  3. GENERATE N layouts from the calibrated generator (real_match + keep_upper=0.9).
  4. Feature vectors for TEST-real vs GENERATED.
  5. KS 2-sample statistic PER FEATURE (TEST vs GEN). Low KS = indistinguishable on that
     feature; KS above the ~0.05 critical value = a 'tell' the generator is off.
  Reports per-feature KS sorted -> exactly where the generator matches / fails real.

Usage: python validate_prior.py --dir <boards> [--n 250]
"""
import sys, os, json, glob, argparse, random, statistics, collections, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import shape_factory as SF
import layout_builder as LB
from mask_to_layout import trim_to_mult3, center
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer


def board_cells(d):
    out = []
    for ly in d.get("layers", []):
        L = ly.get("layer", ly.get("index"))
        for c in ly.get("cells", ly.get("stones", [])):
            try: out.append((L, float(c["x"]), float(c["y"])))
            except (ValueError, KeyError, TypeError): pass
    return out


def feats(cells):
    by = collections.defaultdict(list)
    for L, x, y in cells: by[L].append((x, y))
    base = by.get(0, [])
    if len(base) < 3: return None
    xs = [x for _, x, y in cells]; ys = [y for _, x, y in cells]
    bxs = [p[0] for p in base]; bys = [p[1] for p in base]
    bw = int(round(max(bxs) - min(bxs))) + 1; bh = int(round(max(bys) - min(bys))) + 1
    fill = len(base) / (bw * bh)
    # base clusters (4-conn)
    bset = {(round(x), round(y)) for x, y in base}; seen = set(); ncomp = 0
    for c in bset:
        if c in seen: continue
        ncomp += 1; st = [c]; seen.add(c)
        while st:
            x, y = st.pop()
            for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if nb in bset and nb not in seen: seen.add(nb); st.append(nb)
    # tower height mean
    up = [(x, y) for L, x, y in cells if L > 0]
    towers = [sum(1 for (x, y) in up if abs(x-bx) < 1 and abs(y-by_) < 1) for (bx, by_) in base]
    # symmetry h (on base grid)
    g = [[0]*bw for _ in range(bh)]
    for x, y in base: g[int(round(max(bys)-y))][int(round(x-min(bxs)))] = 1
    sym = 1.0 if g == [r[::-1] for r in g] else 0.0
    # layout difficulty
    b = Board("f")
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = -1; ly.cells.append(cc)
        b.layers.append(ly)
    diff = DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))
    return {"n_layers": len(by), "cells": len(cells), "base_fill": round(fill, 3),
            "tower_mean": round(statistics.mean(towers), 2) if towers else 0,
            "n_clusters": ncomp, "sym_h": sym, "aspect": round(bw/bh, 2), "layout_diff": round(diff, 2)}


def ks(a, b):
    """2-sample Kolmogorov-Smirnov statistic (max CDF gap)."""
    a = sorted(a); b = sorted(b); na, nb = len(a), len(b)
    allv = sorted(set(a + b)); d = 0.0; i = j = 0
    for v in allv:
        while i < na and a[i] <= v: i += 1
        while j < nb and b[j] <= v: j += 1
        d = max(d, abs(i/na - j/nb))
    return d


import empirical_gen
def gen_layout(rng):
    return empirical_gen.sample(rng)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--n", type=int, default=250)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "*.json")))
    # 1. dedup
    seen = {}; distinct = []
    for f in files:
        d = json.load(open(f, encoding="utf-8")); cs = board_cells(d)
        if len(cs) < 6: continue
        sig = frozenset((L, round(x, 1), round(y, 1)) for L, x, y in cs)
        if sig in seen: continue
        seen[sig] = 1; distinct.append(cs)
    # 2. split (deterministic by index parity to avoid RNG dependence)
    test = [c for i, c in enumerate(distinct) if i % 5 == 0]      # 20% held-out
    print(f"corpus: {len(files)} files -> {len(distinct)} distinct ({100*(1-len(distinct)/len(files)):.1f}% dup removed); TEST held-out = {len(test)}")
    # 3. sample TEST + generate GEN
    rng = random.Random(7)
    test_s = test if len(test) <= a.n else [test[i] for i in sorted(rng.sample(range(len(test)), a.n))]
    F_test = [f for f in (feats(c) for c in test_s) if f]
    F_gen = []
    tries = 0
    while len(F_gen) < a.n and tries < a.n * 4:
        tries += 1
        c = gen_layout(rng)
        if c:
            ff = feats(c)
            if ff: F_gen.append(ff)
    print(f"TEST-real n={len(F_test)}  GEN n={len(F_gen)}\n")
    # 4. KS per feature
    keys = ["n_layers", "cells", "base_fill", "tower_mean", "n_clusters", "sym_h", "aspect", "layout_diff"]
    crit = 1.36 * math.sqrt((len(F_test)+len(F_gen)) / (len(F_test)*len(F_gen)))   # KS p=0.05 critical
    print(f"KS 2-sample (GEN vs held-out REAL). critical@p=0.05 = {crit:.3f}; KS<crit = indistinguishable")
    print(f"{'feature':<13}{'KS':>6}  {'real median':>12}{'gen median':>12}  verdict")
    rows = []
    for k in keys:
        tv = [f[k] for f in F_test]; gv = [f[k] for f in F_gen]
        d = ks(tv, gv); rows.append((d, k, statistics.median(tv), statistics.median(gv)))
    rows.sort()
    for d, k, rm, gm in rows:
        verdict = "match" if d < crit else ("close" if d < crit*2 else "TELL (off)")
        print(f"{k:<13}{d:>6.3f}  {rm:>12.2f}{gm:>12.2f}  {verdict}")
    ntell = sum(1 for d, k, rm, gm in rows if d >= crit*2)
    print(f"\nSUMMARY: {sum(1 for d,*_ in rows if d<crit)}/{len(rows)} features indistinguishable; {ntell} clear TELLs")
    print("(rigorous: held-out test set, dedup'd corpus, KS 2-sample per feature)")


if __name__ == "__main__":
    main()
