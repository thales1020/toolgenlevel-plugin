"""Consolidated EDA over the competitor corpus (DEDUPED) — the single authoritative pass.
Folds in every metric discovered across the session: counts, fill, cluster count+SIZE,
tower height, stacking offset, symmetry, aspect, capacity, bbox, pickable, cover, difficulty,
diversity, source-level structure. Writes a readable report + refreshes layout_priors.json.

Usage: python eda_full.py --dir <boards> [--diff-sample 1200]
"""
import sys, os, json, glob, argparse, collections, statistics, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer


def board_cells(d):
    out = []
    for ly in d.get("layers", []):
        L = ly.get("layer", ly.get("index"))
        for c in ly.get("cells", ly.get("stones", [])):
            try: out.append((L, float(c["x"]), float(c["y"])))
            except (ValueError, KeyError, TypeError): pass
    return out


def pctl(v, p): return sorted(v)[min(len(v) - 1, int(p * len(v)))]
def med(v): return statistics.median(v)


def diff_of(cells):
    by = {}
    for L, x, y in cells: by.setdefault(L, []).append((x, y))
    b = Board("s")
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = -1; ly.cells.append(cc)
        b.layers.append(ly)
    return DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--diff-sample", type=int, default=1200)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, "*.json")))

    seen = set(); B = []; srcs = collections.Counter()
    raw = 0
    for f in files:
        d = json.load(open(f, encoding="utf-8")); cs = board_cells(d)
        if len(cs) < 6: continue
        raw += 1
        sig = frozenset((L, round(x, 1), round(y, 1)) for L, x, y in cs)
        if sig in seen: continue
        seen.add(sig); B.append((cs, d.get("src_file", "?")))
        srcs[d.get("src_file", "?")] += 1

    layers=[]; cellc=[]; basec=[]; fill=[]; aspect=[]; cap=[]; bw=[]; bh=[]
    ncl=[]; csize=[]; towers=[]; pick=[]; cover=[]; symh=0; symv=0; offset=collections.Counter()
    for cs, src in B:
        by = collections.defaultdict(list)
        for L, x, y in cs: by[L].append((x, y))
        layers.append(len(by)); cellc.append(len(cs)); cap.append(len(cs)//3)
        base = by.get(0, [])
        if len(base) < 1: continue
        basec.append(len(base))
        xs=[x for _,x,y in cs]; ys=[y for _,x,y in cs]
        bbw=int(round(max(xs)-min(xs)))+1; bbh=int(round(max(ys)-min(ys)))+1
        bw.append(bbw); bh.append(bbh); aspect.append(round(bbw/bbh,2))
        bxs=[p[0] for p in base]; bys=[p[1] for p in base]
        gw=int(round(max(bxs)-min(bxs)))+1; gh=int(round(max(bys)-min(bys)))+1
        fill.append(len(base)/(gw*gh))
        # cluster count + size
        bset={(round(x),round(y)) for x,y in base}; vis=set()
        for c in bset:
            if c in vis: continue
            st=[c]; vis.add(c); sz=0
            while st:
                x,y=st.pop(); sz+=1
                for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if nb in bset and nb not in vis: vis.add(nb); st.append(nb)
            csize.append(sz)
        ncl.append(len({0}) and sum(1 for c in bset if c==c))  # placeholder; recompute below
        # recompute ncl cleanly
        vis=set(); nc=0
        for c in bset:
            if c in vis: continue
            nc+=1; st=[c]; vis.add(c)
            while st:
                x,y=st.pop()
                for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                    if nb in bset and nb not in vis: vis.add(nb); st.append(nb)
        ncl[-1]=nc
        # tower height per base cell
        up=[(x,y) for L,x,y in cs if L>0]
        for (px,py) in base: towers.append(sum(1 for (x,y) in up if abs(x-px)<1 and abs(y-py)<1))
        # symmetry on base grid
        g=[[0]*gw for _ in range(gh)]
        for x,y in base: g[int(round(max(bys)-y))][int(round(x-min(bxs)))]=1
        if g==[r[::-1] for r in g]: symh+=1
        if g==g[::-1]: symv+=1
        # pickable + cover
        npick=nbur=0
        for (L,x,y) in cs:
            cov=any(L2>L and abs(x2-x)<1 and abs(y2-y)<1 for (L2,x2,y2) in cs)
            if cov: nbur+=1
            else: npick+=1
        pick.append(npick); cover.append(round(nbur/len(cs),2))
        # stacking offset (sample, cheap)
        if len(offset)<200000:
            for L,x,y in cs:
                if L>0 and by.get(L-1):
                    bx,by_=min(by[L-1],key=lambda p:abs(p[0]-x)+abs(p[1]-y))
                    offset[(round(abs(x-bx),1),round(abs(y-by_),1))]+=1

    # difficulty on a sample
    step=max(1,len(B)//a.diff_sample); diffs=[]
    for i,(cs,_) in enumerate(B):
        if i%step: continue
        try: diffs.append(diff_of(cs))
        except Exception: pass

    n=len(B)
    R = lambda label, v: print(f"  {label:<22} med {med(v):>6.1f}  mean {statistics.mean(v):>6.1f}  p10 {pctl(v,.1):>5}  p90 {pctl(v,.9):>5}")
    print(f"=== CONSOLIDATED EDA (deduped) — {n} distinct / {raw} non-empty ({100*(1-n/raw):.1f}% dup) ===")
    print("SIZE")
    R("cell_count", cellc); R("base(layer0) cells", basec); R("capacity(/3)", cap)
    R("bbox width", bw); R("bbox height", bh)
    print("SHAPE")
    print(f"  layer_count %         {dict(sorted(collections.Counter(layers).items()))}")
    R("aspect (w/h ×100)", [int(x*100) for x in aspect])
    print(f"  base fill: med {med(fill):.2f} p10 {pctl(fill,.1):.2f} p90 {pctl(fill,.9):.2f}  solid>0.7 {100*sum(1 for v in fill if v>0.7)/len(fill):.0f}%")
    print(f"  symmetry: h {100*symh/n:.0f}%  v {100*symv/n:.0f}%")
    print("CLUSTERS")
    R("clusters/board", ncl)
    cs_h=collections.Counter(min(c,6) for c in csize); ct=len(csize)
    print(f"  cluster SIZE: med {med(csize):.0f} mean {statistics.mean(csize):.2f}  dist: " +
          " ".join(f"{k}{'+' if k==6 else ''}:{100*cs_h[k]/ct:.0f}%" for k in range(1,7)))
    print("STACKING")
    R("tower height/cell", towers)
    ot=sum(offset.values())
    print(f"  offset upper->below: " + " ".join(f"{k}:{100*v/ot:.0f}%" for k,v in offset.most_common(4)))
    print("PLAYABILITY")
    R("pickable at start", pick)
    print(f"  cover ratio: med {med(cover):.2f} p90 {pctl(cover,.9):.2f}")
    print(f"  layout-difficulty (sample {len(diffs)}): med {med(diffs):.2f} mean {statistics.mean(diffs):.2f} p90 {pctl(diffs,.9):.2f} max {max(diffs):.1f}")
    print("META")
    print(f"  source levels: {len(srcs)} (~{int(med(list(srcs.values())))} boards/level)")
    print(f"  diversity: {n} distinct = {100*n/raw:.1f}% unique")

    priors={"source":"tile_explorer_boards","deduped":True,"n_distinct":n,"n_raw":raw,
        "layer_count_dist":{str(k):round(v/n,4) for k,v in sorted(collections.Counter(layers).items())},
        "cell_count":{"median":med(cellc),"p10":pctl(cellc,.1),"p90":pctl(cellc,.9)},
        "base_cells":{"median":med(basec)},"capacity":{"median":med(cap)},
        "bbox":{"w_median":med(bw),"h_median":med(bh)},"aspect_median":med(aspect),
        "base_fill":{"median":round(med(fill),3),"p10":round(pctl(fill,.1),3),"p90":round(pctl(fill,.9),3)},
        "symmetry_rate":{"h":round(symh/n,3),"v":round(symv/n,3)},
        "clusters_per_board":{"median":med(ncl)},
        "cluster_size":{"median":med(csize),"mean":round(statistics.mean(csize),2),
            "dist":{str(k):round(cs_h[k]/ct,3) for k in range(1,7)}},
        "tower_height":{"median":med(towers),"mean":round(statistics.mean(towers),2)},
        "stacking_offset":{f"{k[0]},{k[1]}":round(v/ot,3) for k,v in offset.most_common(4)},
        "pickable_start":{"median":med(pick)},"cover_ratio_median":med(cover),
        "layout_difficulty":{"median":round(med(diffs),2),"mean":round(statistics.mean(diffs),2),"p90":round(pctl(diffs,.9),2)},
        "diversity_unique_pct":round(100*n/raw,1),"source_levels":len(srcs)}
    out=os.path.join(os.path.dirname(HERE),"layout_priors.json")
    json.dump(priors,open(out,"w",encoding="utf-8"),indent=2,ensure_ascii=False)
    print(f"\nSAVED refreshed priors -> {out}")


if __name__ == "__main__":
    main()
