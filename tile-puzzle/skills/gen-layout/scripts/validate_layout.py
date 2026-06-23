"""Validate an icon-generated layout is USABLE for level-gen.

Structural checks (always) + optional v3-solvable gold standard (--solve):
gen tiles with TEEngine, confirm solve_v3 == True (the project's always-solvable bar).

Usage: python validate_layout.py --in NewLayout_icon.json [--solve] [--samples 5] [--json]
"""
import sys, os, json, argparse, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ENG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine")
sys.path.insert(0, ENG)
from tile_level_simulator import Board, Layer, Cell, TEEngine, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3


def board_from_json(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    b = Board(d.get("metadata", {}).get("layout", "icon"))
    for ly in sorted(d["layers"], key=lambda l: l["index"]):
        L = Layer(ly["index"])
        for s in ly["stones"]:
            c = Cell(float(s["x"]), float(s["y"]), ly["index"])
            c.tile_id = int(s.get("i", -1))
            L.cells.append(c)
        b.layers.append(L)
    return b, d


def covers(a, b):  # does higher-layer cell a cover lower cell b?
    return a.layer_idx > b.layer_idx and abs(a.x - b.x) < 1.0 and abs(a.y - b.y) < 1.0


def _overlap(c, o):
    return max(0.0, 1.0 - abs(c.x - o.x)) * max(0.0, 1.0 - abs(c.y - o.y))


def structural(b, support_thresh=0.5):
    cells = b.all_cells()
    n = len(cells)
    pickable = 0
    floating = 0
    for c in cells:
        higher = [o for o in cells if covers(o, c)]
        if not higher:
            pickable += 1
        # no-floating: a non-base cell must REST on the layer below by >= support_thresh
        # AREA (matches uniform_stagger builder; real layouts have edge cells on only
        # 2 supporters, so the old "needs 4 supporters" rule was wrong).
        if c.layer_idx > 0:
            support = sum(_overlap(c, o) for o in cells
                          if o.layer_idx == c.layer_idx - 1 and abs(o.x - c.x) < 1.0 and abs(o.y - c.y) < 1.0)
            if support < support_thresh - 1e-9:
                floating += 1
    buried = sum(1 for c in cells if any(covers(o, c) for o in cells))
    return dict(total=n, capacity=n // 3, div3=(n % 3 == 0),
                pickable=pickable, buried=buried,
                cover_ratio=round(buried / n, 2) if n else 0, floating=floating)


def try_solvable(b, samples, cap):
    weights = load_scoring_weights()
    best = None
    for s in range(samples):
        random.seed(1000 + s)
        for c in b.all_cells():
            c.tile_id = -1
        eng = TEEngine(); eng.validate = False
        eng.color_count = random.choice([3, 4, 5])
        eng.generate(b)
        res, depth, exp = solve_v3(b, max_expansions=cap, verbose=False)
        if res is None:
            res, depth, exp = solve_v3(b, max_expansions=cap * 2, verbose=False)
        if res is True:
            sc = DifficultyScorer.compute_full_score(b, weights=weights)["final_score"]
            return True, s, round(sc, 1), depth, exp
        best = (res, s, None, depth, exp)
    return (False,) + (best[1:] if best else (None, None, None, None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--cap", type=int, default=100000)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    b, d = board_from_json(a.inp)
    st = structural(b)
    out = {"structural": st}
    ok = st["div3"] and st["capacity"] >= 2 and st["pickable"] >= 3 and st["floating"] == 0
    if a.solve:
        solv, seed, score, depth, exp = try_solvable(b, a.samples, a.cap)
        out["solvable"] = dict(result=solv, seed=seed, score=score, depth=depth, expansions=exp)
        ok = ok and solv

    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"{'PASS' if ok else 'FAIL'}  {st}")
        if a.solve:
            s = out["solvable"]
            print(f"  solvable: {s['result']} (seed={s['seed']} score={s['score']} "
                  f"depth={s['depth']} exp={s['expansions']})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
