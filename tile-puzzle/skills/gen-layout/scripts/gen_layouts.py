"""Layout-gen driver — ONE empty layout from a Claude-authored compose spec.

Bulk generation was RETIRED (empirical / abstract / symmetric / mixed modes + their data banks):
per-board symmetry and aesthetics could not be guaranteed at scale (empirical kept only ~8% of
boards perfectly symmetric vs ~66% for real boards). gen-layout now does ONE well-composed,
symmetry-RANKED layout at a time. Symmetry is measured on 4 axes (vertical, horizontal, diag /,
diag \\) and reported — prioritised but never forced ("đo & xếp hạng, không ép").

compose flow: Claude authors a spec (tower anchors + heights, optional mirror axis); this renders
coordinates with the +0.5 stagger + support cleanup, trims to a multiple of 3 (symmetry-preserving
when mirrored), then scores the 4 symmetry axes into metadata.

Usage:
  python gen_layouts.py --mode compose --spec '[[0,0,3],[1,1,2]]' --name heart --out layouts/
  python gen_layouts.py --mode compose --spec '...' --no-mirror --name sword --out layouts/
  python gen_layouts.py --mode compose --spec '...' --axis horizontal --name fish --out layouts/
"""
import sys, os, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from mask_to_layout import to_stones
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer


def to_board(cells):
    b = Board("c"); by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            c = Cell(x, y, L); c.tile_id = -1; ly.cells.append(c)
        b.layers.append(ly)
    return b


def layout_diff(cells):
    b = to_board([(c[0], c[1], c[2]) for c in cells])
    return DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))


def _overlap(ax, ay, bx, by):
    return max(0.0, 1.0 - abs(ax - bx)) * max(0.0, 1.0 - abs(ay - by))


def structural_ok(cells):
    """div3, pickable>=3, no floating. No-floating uses the GAME's cover rule: an upper cell
    must OVERLAP >=1 cell directly below (|dx|<1 & |dy|<1) — NOT a 0.5-area guard (which forbade
    real single-cell +0.5 towers; 72% of real upper cells sit on a corner = 0.25 overlap). Cells=[(L,x,y)]."""
    n = len(cells)
    if n < 6 or n % 3 != 0:
        return False
    by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    for L, x, y in cells:
        if L == 0:
            continue
        if not any(abs(x - bx) < 1 and abs(y - by_) < 1 for (bx, by_) in by.get(L - 1, [])):
            return False
    cl = list(cells)
    pickable = 0
    for (L, x, y) in cl:
        covered = any(L2 > L and abs(x2 - x) < 1 and abs(y2 - y) < 1 for (L2, x2, y2) in cl)
        if not covered:
            pickable += 1
        if pickable >= 3:
            break
    return pickable >= 3


def main():
    ap = argparse.ArgumentParser(description="Compose ONE empty layout from a Claude-authored spec.")
    ap.add_argument("--mode", choices=["compose"], default="compose",
                    help="compose=Claude-authored spec via claude_compose (the only mode; bulk retired)")
    ap.add_argument("--spec", default="", help="JSON list of [x,y,height] tower anchors")
    ap.add_argument("--name", default="", help="layout name")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--mirror", action="store_true", default=True,
                    help="apply symmetry mirror across --axis (default on)")
    ap.add_argument("--no-mirror", dest="mirror", action="store_false",
                    help="elongated/asymmetric shapes (sword, key): no mirror, diagonal-friendly trim")
    ap.add_argument("--axis", choices=["vertical", "horizontal"], default="vertical",
                    help="mirror axis: vertical=left-right (portrait default), horizontal=top-bottom")
    ap.add_argument("--min-sym", type=float, default=0.0,
                    help="if >0, warn (exit 2) when the best of the 4 symmetry axes < this; lets "
                         "Claude re-compose. 0 = report only (never forces).")
    a = ap.parse_args()

    import claude_compose as CC
    from geom import sym_scores, best_axis
    os.makedirs(a.out, exist_ok=True)
    if not a.spec:
        print("ERROR: --mode compose requires --spec '[[x,y,h],...]'")
        return 1
    try:
        spec = json.loads(a.spec)
    except json.JSONDecodeError as e:
        print(f"ERROR: --spec must be valid JSON: {e}")
        return 1

    cells = CC.compose(spec, mirror=a.mirror, axis=a.axis)
    if not cells:
        print("ERROR: compose() returned empty cell list (check spec + support rules)")
        return 1

    name = a.name or "compose_layout"
    data = to_stones([list(c) for c in cells], name)
    d = layout_diff(cells)
    scores = sym_scores(cells)
    bax, bscore = best_axis(cells)
    data["metadata"].update({
        "layout_difficulty": round(d, 2),
        "source": "claude_compose",
        "symmetry_axes": scores,            # {vertical, horizontal, diag_main, diag_anti}
        "symmetry_best_axis": bax,
        "symmetry_score": bscore,           # max of the 4 axes
    })
    out_path = os.path.join(a.out, f"NewLayout_{name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    sym_str = "  ".join(f"{k[:4]}={v:.2f}" for k, v in scores.items())
    print(f"compose -> {out_path}")
    print(f"  {len(cells)} cells, {max(c[0] for c in cells)+1} layers, layout_diff={d:.2f}")
    print(f"  symmetry: {sym_str}  -> best {bax}={bscore:.2f}")
    if a.min_sym > 0 and bscore < a.min_sym:
        print(f"  WARNING: best symmetry {bscore:.2f} < --min-sym {a.min_sym:.2f} — consider re-composing.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
