"""Full acceptance suite (beyond the per-use-case smoke test) — robustness, determinism,
end-to-end layout->level->solvable, bulk integrity, output-format. Run before calling the
skill 'final'. Prints a categorized PASS/FAIL report.

Usage: python test_full.py
"""
import sys, os, random, json, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
import shape_factory as SF
import layout_builder as LB
import gen_layouts as GL
from maskio import load_mask, hole_count
from mask_to_layout import build_cells, trim_to_mult3, center, to_stones
import evaluate_icon as EV
from tile_level_simulator import Board, Layer, Cell, TEEngine, DifficultyScorer, load_scoring_weights
from verify_smart_v3 import solve_v3
W = load_scoring_weights()
R = []
def rec(cat, name, ok, note=""): R.append((cat, name, "PASS" if ok else "FAIL", note))

def board(cells):
    b = Board("t"); by = {}
    for L, x, y in cells: by.setdefault(L, []).append((x, y))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            c = Cell(x, y, L); c.tile_id = -1; ly.cells.append(c)
        b.layers.append(ly)
    return b

# ---------- A. ROBUSTNESS / graceful failure + gate rejection ----------
try:
    out = LB.build([[0, 0], [0, 0]], max_layers=3)        # empty mask
    rec("robust", "empty mask -> no cells (no crash)", out == [], f"got {len(out)} cells")
except Exception as e:
    rec("robust", "empty mask -> no cells (no crash)", False, f"crashed {type(e).__name__}")
try:
    cells, _ = build_cells([[1, 1], [1, 1]], max_layers=2)  # tiny 2x2
    cells, _ = trim_to_mult3(cells)
    rec("robust", "tiny 2x2 mask handled", True, f"{len(cells)} cells")
except Exception as e:
    rec("robust", "tiny 2x2 mask handled", False, f"{type(e).__name__}: {e}")
# gate must REJECT a thin/complex shape (evaluate -> (verdict, metrics, reasons))
try:
    thin = [[1 if (x == 0 or y == 0) else 0 for x in range(12)] for y in range(12)]  # thin L
    verdict = EV.evaluate(thin)[0]
    rec("robust", "gate rejects thin shape (too-complex)", verdict == "too-complex", f"verdict={verdict}")
except Exception as e:
    rec("robust", "gate rejects thin shape (too-complex)", False, f"{type(e).__name__}: {e}")
# structural_ok must REJECT non-div3 and floating
try:
    good = [(0, 0, 0), (0, 1, 0), (0, 0, -1), (0, 1, -1), (1, 0.5, -0.5)] * 1
    base9 = [(0, x, -y) for x in range(3) for y in range(3)]
    nondiv = base9[:7]  # 7 cells, not div3
    floating = base9 + [(2, 0.5, -0.5)]  # layer-2 cell with no layer-1 below -> floating
    rec("robust", "structural rejects non-div3", not GL.structural_ok(nondiv), f"7 cells")
    rec("robust", "structural rejects floating", not GL.structural_ok(floating), "L2 w/o support")
except Exception as e:
    rec("robust", "structural negative tests", False, f"{type(e).__name__}: {e}")

# ---------- B. DETERMINISM ----------
try:
    a1 = LB.build(SF.spaced_clusters(random.Random(5)), max_layers=6, keep_upper=0.9, seed=5)
    a2 = LB.build(SF.spaced_clusters(random.Random(5)), max_layers=6, keep_upper=0.9, seed=5)
    rec("determinism", "build same seed -> identical", a1 == a2, f"{len(a1)} cells")
except Exception as e:
    rec("determinism", "build same seed -> identical", False, f"{type(e).__name__}: {e}")

# ---------- C. END-TO-END: layout -> assign tiles -> v3-solvable ----------
def shape_solvable(grid, depth, ku=1.0):
    cells = [(c[0], c[1], c[2]) for c in LB.build(grid, max_layers=depth, keep_upper=ku, seed=1)]
    if len(cells) < 12: return None
    cells, _ = trim_to_mult3([list(c) for c in cells]); cells = [(c[0], c[1], c[2]) for c in center(cells)]
    random.seed(1); b = board(cells)
    eng = TEEngine(); eng.validate = False; eng.color_count = 4; eng.generate(b)
    return solve_v3(b, 200000)[0]
for nm, grid, depth, ku in [("circle", SF.circle(6), 3, 1.0),
                            ("real_match", SF.spaced_clusters(random.Random(2)), 6, 0.9),
                            ("ring", SF.ring(7, 3), 3, 1.0),
                            ("scattered", SF.scattered(random.Random(3), n_clusters=4), 4, 1.0)]:
    try:
        r = shape_solvable(grid, depth, ku)
        rec("end2end", f"{nm} -> tiles -> v3-solvable", r is True, f"v3={r}")
    except Exception as e:
        rec("end2end", f"{nm} -> tiles -> v3-solvable", False, f"{type(e).__name__}: {e}")

# ---------- D. BULK INTEGRITY (gen_layouts logic, N=30) ----------
try:
    rng = random.Random(7); kept = []; seen = set(); bad = 0
    while len(kept) < 30 and len(seen) < 600:
        g = SF.spaced_clusters(rng, n_clusters=rng.randint(3, 5))
        res = GL.build_in_band(g, 4, 8, keep_upper=0.9, seed=rng.randint(1, 99999))
        if not res: continue
        cells, d = res; ct = [(c[0], c[1], c[2]) for c in cells]
        sig = SF.exact_sig(ct)
        if sig in seen: continue
        seen.add(sig)
        if not GL.structural_ok(ct) or len(ct) % 3 != 0: bad += 1; continue
        kept.append((ct, d))
    allgood = len(kept) == 30 and bad == 0 and all(4 - 0.3 <= d <= 8 + 0.3 for _, d in kept)
    rec("bulk", "gen 30 distinct, all structural+div3+in-band", allgood, f"kept={len(kept)} bad={bad}")
except Exception as e:
    rec("bulk", "gen 30 distinct", False, f"{type(e).__name__}: {e}")

# ---------- E. OUTPUT FORMAT (empty layout contract) ----------
try:
    cells = [(c[0], c[1], c[2]) for c in LB.build(SF.circle(6), max_layers=3)]
    cells, _ = trim_to_mult3([list(c) for c in cells])
    data = to_stones([list(c) for c in cells], "fmt")
    stones = [s for ly in data["layers"] for s in ly["stones"]]
    no_i = all("i" not in s for s in stones)
    empty_stacks = data["stacks"] == []
    has_meta = "metadata" in data and data["metadata"].get("divisible_by_3") is True
    rec("format", "stones empty (no 'i'), stacks=[], metadata ok", no_i and empty_stacks and has_meta,
        f"no_i={no_i} stacks={empty_stacks} meta={has_meta}")
except Exception as e:
    rec("format", "output format contract", False, f"{type(e).__name__}: {e}")

# ---------- report ----------
print(f"\n{'category':<12}{'check':<46}{'status':<7}note")
print("-" * 100)
cats = {}
for cat, name, st, note in R:
    print(f"{cat:<12}{name:<46}{st:<7}{note}")
    cats.setdefault(cat, []).append(st)
print("-" * 100)
npass = sum(1 for r in R if r[2] == "PASS")
bycat = {c: f"{v.count('PASS')}/{len(v)}" for c, v in cats.items()}
print(f"{npass}/{len(R)} PASS  by-category: {bycat}")
sys.exit(0 if npass == len(R) else 1)
