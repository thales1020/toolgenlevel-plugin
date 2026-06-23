"""Gen a layout whose difficulty (with tiles assigned) targets X.

Difficulty is a property of a LEVEL (tiles assigned), so we estimate it by
assigning tiles via TEEngine over a few seeds and averaging compute_full_score.
Search over (grid, layers) configs, keep solvable candidates, pick the one whose
mean difficulty is closest to the target. Honest: difficulty is a distribution
over tile assignments -> we report avg +- range, hit in expectation.

Usage:
  python target_difficulty.py --mask shape.mask.txt --target 80 [--tol 8] [--out NewLayout.json]
  python target_difficulty.py --icon mdi:hexagon --target 80
"""
import sys, os, json, argparse, random, statistics
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from svg_to_mask import svg_string_to_mask
from fetch_icon import fetch_svg
from maskio import load_mask
import layout_builder as LB
from mask_to_layout import trim_to_mult3, to_stones
from tile_level_simulator import Board, Layer, Cell, TEEngine, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3

WEIGHTS = load_scoring_weights()


def cells_to_board(cells):
    b = Board("cand")
    by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            c = Cell(x, y, L); c.tile_id = -1; ly.cells.append(c)
        b.layers.append(ly)
    return b


def score_layout(cells, color_frac, seeds=3):
    """Assign tiles with color_count = color_frac * capacity (HIGHER colors -> harder,
    fewer copies/type -> fewer easy triples). Return (mean, min, max, solvable_any)."""
    scores = []; solvable = False
    cap = len(cells) // 3
    cc = max(4, min(cap, round(cap * color_frac)))
    for s in range(seeds):
        random.seed(700 + s)
        b = cells_to_board(cells)
        for c in b.all_cells():
            c.tile_id = -1
        eng = TEEngine(); eng.validate = False
        eng.color_count = cc
        eng.generate(b)
        sc = DifficultyScorer.compute_full_score(b, weights=WEIGHTS)["final_score"]
        scores.append(sc)
        if not solvable and solve_v3(b, max_expansions=150000)[0] is True:
            solvable = True
    return statistics.mean(scores), min(scores), max(scores), solvable, cc


def gen_candidate(mask, grid, layers):
    cells = LB.build(mask, mode="uniform_stagger", max_layers=layers)
    cells = [[L, x, y] for (L, x, y) in cells]
    if len(cells) < 6:
        return None
    cells, _ = trim_to_mult3(cells)
    # center
    xs = [c[1] for c in cells]; ys = [c[2] for c in cells]
    cx = round((min(xs)+max(xs))/2*2)/2; cy = round((min(ys)+max(ys))/2*2)/2
    cells = [[L, round(x-cx, 2), round(y-cy, 2)] for (L, x, y) in cells]
    return cells


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mask")
    ap.add_argument("--icon")
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--tol", type=float, default=8)
    ap.add_argument("--out")
    ap.add_argument("--grids", type=int, nargs="*", default=[8, 10, 12])
    ap.add_argument("--layers", type=int, nargs="*", default=[3, 4, 5])
    ap.add_argument("--color-fracs", type=float, nargs="*", default=[0.5, 0.7, 0.9])
    a = ap.parse_args()

    svg = None
    if a.icon:
        svg = fetch_svg(a.icon)
    elif not a.mask:
        raise SystemExit("need --mask or --icon")

    print(f"Target difficulty {a.target} (tol +-{a.tol})  shape={a.icon or a.mask}\n")
    results = []
    for g in a.grids:
        mask = svg_string_to_mask(svg, grid=g) if svg else load_mask(a.mask)
        for L in a.layers:
            cells = gen_candidate(mask, g, L)
            if not cells:
                continue
            for cf in a.color_fracs:
                mean, lo, hi, solv, cc = score_layout(cells, cf)
                tag = "ok " if solv else "UNS"
                print(f"  grid={g} L={L} cells={len(cells):3d} colors={cc:3d}({cf})  "
                      f"diff_avg={mean:5.1f} [{lo:.0f}-{hi:.0f}] {tag}", flush=True)
                if solv:
                    results.append((abs(mean - a.target), mean, lo, hi, g, L, cc, cells))
    if not results:
        raise SystemExit("no solvable candidate")
    results.sort()
    best = results[0]
    _, mean, lo, hi, g, L, cc, cells = best
    print(f"\nBEST: grid={g} layers={L} cells={len(cells)} colors={cc}  diff_avg={mean:.1f} [{lo:.0f}-{hi:.0f}]")
    if best[0] > a.tol:
        print(f"  (closest available; off target by {best[0]:.1f} — difficulty bounded by shape/size)")
    if a.out:
        name = os.path.basename(a.out).replace("NewLayout_", "").replace(".json", "")
        data = to_stones(cells, name)
        data["metadata"]["target_difficulty"] = a.target
        data["metadata"]["est_difficulty_avg"] = round(mean, 1)
        data["metadata"]["est_difficulty_range"] = [round(lo, 1), round(hi, 1)]
        data["metadata"]["suggested_color_count"] = cc
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        print(f"  SAVED {a.out}")


if __name__ == "__main__":
    main()
