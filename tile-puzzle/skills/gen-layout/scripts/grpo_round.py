"""GRPO round harness: a FROM-SCRATCH generator that ENCODES the EXPERIENCES library
(scatter single-cell anchors + towers, per the learned rules) — NOT template-copying.
Generates a batch, scores each vs held-out real boards (KS 2-sample per feature), prints the
loser signal. Claude reads the KS table, updates EXPERIENCES (and the PARAMS below), reruns
until KS converges. This is the Training-Free GRPO loop with Claude as the policy.

Usage: python grpo_round.py --dir <boards> --n 250
"""
import sys, os, json, glob, argparse, random, statistics, math, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer

# ============ EXPERIENCE-ENCODED GENERATOR (edit these between rounds = updating experiences) ============
P = dict(
    sym_prob=0.64,                 # [3] h-symmetry rate
    full_w=[5, 6, 6, 7],           # [7] aspect ~0.84 + spread
    rows=[6, 7, 7, 8],            # [7] (KS needs spread, not just median)
    n_anchor=(14, 24),             # [1] wide -> cells spread 50-100 like real
    cluster2_prob=0.30,            # [1] ~30% neighbor -> cluster-size median 1
    heights=(2, 9),                # [6] tower heights (wide for layer/diff spread)
    height_mean=3.4, height_sd=2.1,  # tower ~4 + wide spread
)

def _place(rng, xr, rows, n):
    a = set()
    for _ in range(n):
        x = rng.randint(*xr); y = rng.randint(0, rows - 1)
        a.add((x, y))
        if rng.random() < P["cluster2_prob"]:
            a.add((x + rng.choice([-1, 0, 1]), y + rng.choice([-1, 0, 1])))
    return a

def gen(rng):
    fw = rng.choice(P["full_w"]); rows = rng.choice(P["rows"])
    sym = rng.random() < P["sym_prob"]
    if sym:
        half = fw // 2
        left = _place(rng, (0, max(0, half - 1)), rows, rng.randint(*P["n_anchor"]) // 2 + 1)
        anchors = set(left) | {(fw - 1 - x, y) for (x, y) in left}   # exact h-mirror
    else:
        anchors = _place(rng, (0, fw - 1), rows, rng.randint(*P["n_anchor"]))
    cells = []
    for (ax, ay) in anchors:
        h = min(P["heights"][1], max(P["heights"][0], round(rng.gauss(P["height_mean"], P["height_sd"]))))
        for L in range(h):
            s = 0.5 if (L % 2) else 0.0
            cells.append((L, round(ax + s, 2), round(-(ay + s), 2)))
    cells = list({c for c in cells})
    # support cleanup
    ch = True
    while ch:
        ch = False; by = {}
        for L, x, y in cells: by.setdefault(L, []).append((x, y))
        keep = []
        for (L, x, y) in cells:
            if L == 0 or any(abs(x-bx) < 1 and abs(y-by_) < 1 for (bx, by_) in by.get(L-1, [])): keep.append((L, x, y))
            else: ch = True
        cells = keep
    if len(cells) < 12: return None
    rem = len(cells) % 3
    if rem:
        top = max(c[0] for c in cells); tops = sorted([c for c in cells if c[0] == top], key=lambda c:-(c[1]**2+c[2]**2))
        drop = set(id(c) for c in tops[:rem]); cells = [c for c in cells if id(c) not in drop]
    return cells
# =========================================================================================================

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
    xs=[x for _,x,y in cells]; ys=[y for _,x,y in cells]
    bxs=[p[0] for p in base]; bys=[p[1] for p in base]
    bw=int(round(max(bxs)-min(bxs)))+1; bh=int(round(max(bys)-min(bys)))+1
    fill=len(base)/(bw*bh)
    bset={(round(x),round(y)) for x,y in base}; vis=set(); ncl=0
    for c in bset:
        if c in vis: continue
        ncl+=1; st=[c]; vis.add(c)
        while st:
            x,y=st.pop()
            for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if nb in bset and nb not in vis: vis.add(nb); st.append(nb)
    up=[(x,y) for L,x,y in cells if L>0]
    tow=[sum(1 for (x,y) in up if abs(x-px)<1 and abs(y-py)<1) for (px,py) in base]
    g=[[0]*bw for _ in range(bh)]
    for x,y in base: g[int(round(max(bys)-y))][int(round(x-min(bxs)))]=1
    sym=1.0 if g==[r[::-1] for r in g] else 0.0
    xs2=[x for _,x,y in cells]; ys2=[y for _,x,y in cells]
    W=int(round(max(xs2)-min(xs2)))+1; H=int(round(max(ys2)-min(ys2)))+1
    b=Board('f')
    for L in sorted(by):
        ly=Layer(L)
        for (x,y) in by[L]: cc=Cell(x,y,L);cc.tile_id=-1;ly.cells.append(cc)
        b.layers.append(ly)
    diff=DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))
    return {"n_layers":len(by),"cells":len(cells),"base_fill":round(fill,3),
            "tower_mean":round(statistics.mean(tow),2) if tow else 0,"n_clusters":ncl,
            "sym_h":sym,"aspect":round(W/H,2),"layout_diff":round(diff,2)}

def ks(a,b):
    a=sorted(a); b=sorted(b); na=len(a); nb=len(b); allv=sorted(set(a+b)); d=0; i=j=0
    for v in allv:
        while i<na and a[i]<=v: i+=1
        while j<nb and b[j]<=v: j+=1
        d=max(d,abs(i/na-j/nb))
    return d

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--dir",required=True); ap.add_argument("--n",type=int,default=250)
    a=ap.parse_args()
    seen=set(); test=[]
    for i,f in enumerate(sorted(glob.glob(os.path.join(a.dir,"*.json")))):
        d=json.load(open(f,encoding="utf-8")); cs=board_cells(d)
        if len(cs)<6: continue
        sig=frozenset((L,round(x,1),round(y,1)) for L,x,y in cs)
        if sig in seen: continue
        seen.add(sig)
        if i%5==0: test.append(cs)
    rng=random.Random(7)
    Ft=[f for f in (feats(c) for c in (test if len(test)<=a.n else random.Random(1).sample(test,a.n))) if f]
    Fg=[]; tries=0
    while len(Fg)<a.n and tries<a.n*4:
        tries+=1; c=gen(rng)
        if c:
            ff=feats(c)
            if ff: Fg.append(ff)
    keys=["n_layers","cells","base_fill","tower_mean","n_clusters","sym_h","aspect","layout_diff"]
    crit=1.36*math.sqrt((len(Ft)+len(Fg))/(len(Ft)*len(Fg)))
    print(f"GEN n={len(Fg)} vs REAL held-out n={len(Ft)}; KS crit={crit:.3f}")
    print(f"{'feature':<13}{'KS':>6}{'real':>8}{'gen':>8}  verdict")
    rows=[]
    for k in keys:
        tv=[f[k] for f in Ft]; gv=[f[k] for f in Fg]; rows.append((ks(tv,gv),k,statistics.median(tv),statistics.median(gv)))
    rows.sort()
    npass=0
    for d,k,rm,gm in rows:
        v="match" if d<crit else ("close" if d<crit*2 else "TELL")
        npass+= d<crit
        print(f"{k:<13}{d:>6.3f}{rm:>8.2f}{gm:>8.2f}  {v}")
    print(f"\n{npass}/8 match  (params: {P})")

if __name__=="__main__":
    main()
