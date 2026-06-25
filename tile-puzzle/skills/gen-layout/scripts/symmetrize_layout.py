"""Enforce EXACT horizontal symmetry on an existing layout (EXP[12] geom-mirror).
Keeps x>0 half + axis, adds geometric mirrors, trims %3 in mirror pairs, validates.
Usage: python symmetrize_layout.py <NewLayout_*.json> <out_name>
"""
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
from mask_to_layout import to_stones, center
from gen_layouts import structural_ok, layout_diff, to_board
from geom import geom_symmetrize, is_geom_sym, geom_div3_trim
from tile_level_simulator import DifficultyScorer as DS
from render_png import layout_to_png

SRC = sys.argv[1]
NAME = sys.argv[2] if len(sys.argv) > 2 else "shield_sym"
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUT = os.path.join(ROOT, "layouts")

d = json.load(open(SRC, encoding="utf-8"))
cells = [(L["index"], round(float(s["x"]), 2), round(float(s["y"]), 2))
         for L in d["layers"] for s in L["stones"]]
print(f"input: {len(cells)} cells, geom_sym={is_geom_sym(cells)}")

cells = geom_symmetrize(cells)                 # exact symmetric (x>0 half + axis, mirrored)
cells = geom_div3_trim(cells)                  # %3==0 keeping symmetry (mirror-pair / axis trims)
cells = [list(c) for c in cells]
cells = center(cells)
# re-round and re-check after center (center may shift x; symmetry axis must remain 0)
cells3 = [(c[0], round(c[1], 2), c[2]) for c in cells]
sym = is_geom_sym(cells3)
ok = structural_ok(cells3)
b = to_board(cells3)
cov = DS.cover100_by_area(b, [id(c) for c in b.all_cells()], 0.9)
nlay = max(c[0] for c in cells3) + 1
diff = layout_diff(cells3)
print(f"output: {len(cells3)} cells, layers={nlay}, geom_sym={sym}, structural_ok={ok}, "
      f"div3={len(cells3)%3==0}, cover100={cov} ({cov/len(cells3)*100:.1f}%), diff={diff:.2f}")

data = to_stones([list(c) for c in cells3], NAME)
data["metadata"].update({"source": "shape_symmetrized", "layout_difficulty": round(diff, 2),
                         "cover100": cov, "h_symmetric": bool(sym)})
path = os.path.join(OUT, f"NewLayout_{NAME}.json")
json.dump(data, open(path, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
from render_png import layout_to_png as _r
_r(path, os.path.join(OUT, f"_{NAME}_stack.png"), ppu=18)
print(f"-> {path}")
print(f"   stack render: layouts/_{NAME}_stack.png")
