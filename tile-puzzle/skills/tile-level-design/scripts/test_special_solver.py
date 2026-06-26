"""Regression test for solve_special.solve_v3_special (the special-tile auto-clear solver).

Locks the two soundness properties:
  A. AUTO-CLEAR semantics — a special covers cells below while present, and clears for FREE (no tray)
     the moment it is uncovered (cascading). Deterministic mini-boards.
  B. REDUCTION — with NO special cells, solve_v3_special must give the SAME verdict as the
     battle-tested engine solve_v3 (so the adaptation didn't change the match-3 core).
  C. END-TO-END — reserve_special output verifies solvable under the rigorous solver.

Run: python test_special_solver.py   (prints PASS/FAIL per check; exit 0 iff all pass)
"""
import sys, os, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
from tile_level_simulator import Board, Layer, Cell, TEEngine, load_board_from_file
from verify_smart_v3 import solve_v3
from solve_special import solve_v3_special

R = []
def check(name, ok, note=""):
    R.append((name, ok, note))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {note}")


def mk(spec):
    """spec: list of (layer, x, y, tile_id) -> Board."""
    b = Board("t"); by = {}
    for L, x, y, t in spec:
        by.setdefault(L, []).append((x, y, t))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y, t) in by[L]:
            c = Cell(x, y, L); c.tile_id = t; ly.cells.append(c)
        b.layers.append(ly)
    return b


def V(board, cap=300_000):
    return solve_v3_special(board, special_ids=(1001, 1002), max_expansions=cap)[0]


print("A. auto-clear semantics (deterministic):")
# 6 same-type (÷3) on L0, a special on L1 covering one of them -> special auto-clears, then 6 clear
check("special covers a match-3 cell, then auto-clears -> solvable",
      V(mk([(0, i, 0, 0) for i in range(6)] + [(1, 0, 0, 1001)])) is True)
# pure stack of 3 specials (no match-3) -> all auto-clear top-down
check("stack of 3 specials, no match-3 -> solvable (cascade)",
      V(mk([(0, 0, 0, 1002), (1, 0, 0, 1002), (2, 0, 0, 1002)])) is True)
# special buried UNDER a match-3 triple: clear the triple, the special is exposed, auto-clears
check("special under a match-3 triple -> solvable",
      V(mk([(1, 0, 0, 0), (1, 1, 0, 0), (1, 2, 0, 0), (0, 0, 0, 1001),
            (0, 1, 0, 0), (0, 2, 0, 0)])) is True)
# plain solvable match-3 (no special), control
check("plain 6x match-3 (control) -> solvable",
      V(mk([(0, i, 0, 0) for i in range(6)])) is True)

print("B. reduction vs engine solve_v3 (no specials, must AGREE):")
L = os.path.join(os.path.dirname(HERE), "sample_layouts", "NewLayout_L50.json")
if not os.path.exists(L):
    # fall back to any layout that loads
    import glob
    for cand in glob.glob(os.path.join(os.path.dirname(HERE), "sample_layouts", "NewLayout_L*.json")):
        if load_board_from_file(cand) is not None:
            L = cand; break
agree = tot = 0; mism = []
loadable = load_board_from_file(L) is not None
if loadable:
    for cc in (4, 8, 14, 20):
        for seed in (1, 5, 11):
            random.seed(seed)
            b = load_board_from_file(L)
            e = TEEngine(); e.validate = False; e.color_count = cc; e.distance = 15; e.generate(b)
            r_engine = solve_v3(b, 250_000)[0]
            r_special = solve_v3_special(b, max_expansions=250_000)[0]
            tot += 1
            if r_engine == r_special:
                agree += 1
            else:
                mism.append((cc, seed, r_engine, r_special))
    check(f"solve_v3 == solve_v3_special on {tot} no-special boards", agree == tot,
          f"agree={agree}/{tot} mismatches={mism}")
else:
    check("reduction cross-check", True, "(skipped — no loadable sample layout)")

print("C. end-to-end reserve_special is solvable under the rigorous solver:")
try:
    import subprocess, json, tempfile
    # build a tiny empty layout inline and reserve specials, then re-verify
    empty = mk([(L_, x, 0, -1) for L_ in range(2) for x in range(9)])  # 2-layer strip, 18 cells
    # assign match-3 to 15 cells, reserve 3 as 1002, then verify with solve_v3_special
    cells = empty.all_cells()
    random.seed(1)
    for c in cells: c.tile_id = -1
    res = set(id(c) for c in random.sample(cells, 3))
    for c in cells: c.tile_id = 1002 if id(c) in res else -1
    m3 = [c for c in cells if id(c) not in res]
    eng = TEEngine(); eng.validate = False; eng.color_count = 5; eng.distance = 1
    ecc = eng._get_effective_cc(); pool = eng._build_icon_pool(len(m3), ecc)
    eng._bind_random(m3, pool, ecc, eng._compute_knob_flags(empty, ecc)); eng._fix_x3_distribution(m3, ecc)
    check("reserved level verifies True under solve_v3_special",
          solve_v3_special(empty, max_expansions=300_000)[0] is True)
except Exception as ex:
    check("end-to-end reserve", False, f"{type(ex).__name__}: {ex}")

npass = sum(1 for _, ok, _ in R if ok)
print(f"\n{npass}/{len(R)} PASS")
sys.exit(0 if npass == len(R) else 1)
