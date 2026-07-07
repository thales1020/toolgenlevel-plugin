"""Add SPECIAL tiles (bonus 1001 / mission 1002) to a layout — the CORRECT way (direction C).

Reverse-engineered from the BonusLevel + MissionTile reference data:
  - The NORMAL tiles are a COMPLETE ÷3 match-3 set on their own (52/52 reference files: normal-count is
    ÷3). Specials are NOT reserved match-3 slots — they are ADDITIONAL cover stones sitting at their OWN
    interstitial positions, and they never consume a normal cell.
  - A special is a big DECORATIVE frame but collides as a 1×1 unit (engine / Unity IsCanPickUp:
    `|dx|<1 & |dy|<1`, same for every tile). Placed at a 2×2 CENTRE (half-integer x,y) on a layer just
    above that 2×2, it covers exactly those 4 normals and auto-clears once nothing covers IT.

Algorithm:
  1. Assign a full NORMAL match-3 level on the layout (all cells, trimmed to ÷3), verified v3-solvable.
  2. Renumber normals onto EVEN layers (layer_idx*2); place each special on the ODD layer between,
     at a 2×2 centre, chosen so a higher NORMAL still covers it at start (so it does NOT auto-clear
     immediately). No normal is removed — the match-3 set stays ÷3.
  3. Verify on the FULL board with solve_v3_special (rigorous: specials as covers + auto-clear), assert
     every special is COVERED at start, assert normals ÷3.

These tiles are OPTIONAL — only run this when the design asks for bonus/mission tiles.

Usage:
  python reserve_special.py <empty_layout.json> --bonus N --mission M [--size S]
       [--out o.json] [--color-count 10] [--distance 2] [--seeds 40] [--smin S --smax S]
  # legacy single-special form still works:  --id 1001|1002 --n N
"""
import sys, os, json, argparse, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
sys.path.insert(0, HERE)
from tile_level_simulator import load_board_from_file, TEEngine, DifficultyScorer, Board, Layer, Cell
from verify_smart_v3 import solve_v3, build_bitmask_visibility
from solve_special import solve_v3_special

WEIGHTS = json.load(open(os.path.join(os.path.dirname(HERE), "engine", "scoring_weights.json"), encoding="utf-8"))

# Render size 's' (cosmetic — collision is 1×1 regardless). BONUS (1001): always 1.5. MISSION (1002):
# VARIED — the L30-120 "mixed" style (base 0.6, occasional 0.9/1.2). --size overrides all.
BONUS_SIZE = 1.5
_MISSION_SIZE_DIST = [(0.6, 60), (0.55, 13), (0.9, 19), (0.95, 3), (1.2, 5)]


def _mission_size(rng):
    total = sum(w for _, w in _MISSION_SIZE_DIST)
    r = rng.uniform(0, total); acc = 0
    for v, w in _MISSION_SIZE_DIST:
        acc += w
        if r < acc:
            return v
    return _MISSION_SIZE_DIST[0][0]


def _covered(c, cells):
    """A normal cell has something on a higher layer overlapping it (|dx|<1 & |dy|<1)."""
    return any(o.layer_idx > c.layer_idx and abs(o.x - c.x) < 1 and abs(o.y - c.y) < 1 for o in cells)


def _gen_normal_level(layout, cc, distance, seed):
    """Full NORMAL match-3 level on `layout`, trimmed to ÷3, v3-solvable. Board or None."""
    random.seed(seed)
    board = load_board_from_file(layout)
    board.clear_tiles()
    cells = board.all_cells()
    rem = len(cells) % 3
    if rem:                                   # trim ÷3 by dropping fully-exposed cells
        ex = [c for c in cells if not _covered(c, cells)]
        random.shuffle(ex)
        drop = set(id(c) for c in ex[:rem])
        for ly in board.layers:
            ly.cells = [c for c in ly.cells if id(c) not in drop]
        cells = board.all_cells()
    eng = TEEngine(); eng.validate = False
    eng.color_count = cc; eng.hard_code = 0; eng.distance = distance
    eff = eng._get_effective_cc()
    pool = eng._build_icon_pool(len(cells), eff)
    flags = eng._compute_knob_flags(board, eff)
    eng._bind_random(cells, pool, eff, flags)
    eng._fix_x3_distribution(cells, eff)
    if solve_v3(board, 200_000)[0] is not True:
        return None
    if solve_v3(board, 2_000_000)[0] is not True:
        return None
    return board


def _find_placements(board, rng):
    """Candidate special sites: a 2×2 of normals on layer L whose CENTRE is still covered by a higher
    normal. Returns [(coveredness, cx, cy, L)]. Ordered so specials sit HIGH in the stack and are
    LIGHTLY covered — like the game, a big mission/bonus should stay VISIBLE (a couple of tiles resting
    on it), not be buried at the bottom. It still needs cov≥1 so it doesn't auto-clear at level start."""
    cells = board.all_cells()
    by_layer = {}
    for c in cells:
        by_layer.setdefault(c.layer_idx, set()).add((round(c.x, 3), round(c.y, 3)))
    cand = []
    for L, pts in by_layer.items():
        for (x, y) in pts:
            if (x + 1, y) in pts and (x, y + 1) in pts and (x + 1, y + 1) in pts:
                cx, cy = x + 0.5, y + 0.5
                # coverers above (2×2 footprint, radius 1.5) — need ≥1 so it stays covered at start
                cov = sum(1 for c in cells if c.layer_idx > L and abs(c.x - cx) < 1.5 and abs(c.y - cy) < 1.5)
                if cov > 0:
                    cand.append((cov, cx, cy, L))
    rng.shuffle(cand)
    cand.sort(key=lambda t: (-t[3], t[0]))   # highest cluster-layer first, then FEWEST coverers (visible)
    return cand


def _build_with_specials(normal_board, placements):
    """placements: [(cx,cy,L,sid)]. New board: normals on EVEN layers (2*L), specials on ODD (2L+1)."""
    by = {}
    for c in normal_board.all_cells():
        by.setdefault(2 * c.layer_idx, []).append((c.x, c.y, c.tile_id))
    for (cx, cy, L, sid) in placements:
        by.setdefault(2 * L + 1, []).append((cx, cy, sid))
    b = Board("special")
    for L in sorted(by):
        ly = Layer(L)
        for (x, y, t) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = t; ly.cells.append(cc)
        b.layers.append(ly)
    return b


def _all_specials_covered(board, sids):
    """Every special is COVERED at start by a NORMAL on its 2×2 footprint (radius 1.5), so it stays
    visible + won't auto-clear immediately (matches the player's 2×2 special-collision model)."""
    cells = board.all_cells()
    for sc in cells:
        if sc.tile_id in sids:
            if not any(c.tile_id not in sids and c.layer_idx > sc.layer_idx
                       and abs(c.x - sc.x) < 1.5 and abs(c.y - sc.y) < 1.5 for c in cells):
                return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Add bonus/mission special tiles as interstitial 2×2 covers (direction C).")
    ap.add_argument("layout", help="EMPTY layout JSON (no tiles)")
    ap.add_argument("--id", type=int, default=None, help="legacy single special id: 1001 bonus / 1002 mission")
    ap.add_argument("--n", type=int, default=None, help="count for --id")
    ap.add_argument("--bonus", type=int, default=0, help="how many BONUS (1001) tiles to add")
    ap.add_argument("--mission", type=int, default=0, help="how many MISSION (1002) tiles to add")
    ap.add_argument("--size", type=float, default=None,
                    help="render size 's' OVERRIDE for ALL specials. Omit = bonus 1.5, mission MIXED "
                         "(L30-120 style). s is cosmetic — collision is 1×1, the round shape comes from id.")
    ap.add_argument("--color-count", type=int, default=10)
    ap.add_argument("--distance", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=40, help="seeds to try")
    ap.add_argument("--smin", type=float, default=None, help="optional min normal-board final_score")
    ap.add_argument("--smax", type=float, default=None, help="optional max normal-board final_score")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    reserve_spec = {}
    if a.id is not None:
        if a.n is None:
            raise SystemExit("--id requires --n")
        reserve_spec[a.id] = reserve_spec.get(a.id, 0) + a.n
    if a.bonus:
        reserve_spec[1001] = reserve_spec.get(1001, 0) + a.bonus
    if a.mission:
        reserve_spec[1002] = reserve_spec.get(1002, 0) + a.mission
    if not reserve_spec:
        raise SystemExit("specify --bonus N and/or --mission M (or the legacy --id ID --n N)")
    sids = tuple(sorted(reserve_spec))
    sids_set = set(sids)
    # ordered special-id list (bonus first, then mission), one entry per tile to place
    want = []
    for sid in sorted(reserve_spec):
        want += [sid] * reserve_spec[sid]
    n_special = len(want)

    best_placed = 0
    for seed in range(1, a.seeds + 1):
        nb = _gen_normal_level(a.layout, a.color_count, a.distance, seed)
        if nb is None:
            continue
        # optional score band on the NORMAL board
        fs = DifficultyScorer.compute_full_score(nb, WEIGHTS)["final_score"]
        if (a.smin is not None and fs < a.smin) or (a.smax is not None and fs > a.smax):
            continue
        rng = random.Random(seed * 131 + 7)
        cand = _find_placements(nb, rng)
        # pick n_special well-separated centres (footprints not overlapping each other)
        chosen = []
        for (cov, cx, cy, L) in cand:
            if all(abs(cx - px) >= 2 or abs(cy - py) >= 2 for (px, py, _) in chosen):
                chosen.append((cx, cy, L))
            if len(chosen) == n_special:
                break
        best_placed = max(best_placed, len(chosen))
        if len(chosen) < n_special:
            continue                       # this seed can't host them all — try another
        placements = [(cx, cy, L, sid) for (cx, cy, L), sid in zip(chosen, want)]
        board = _build_with_specials(nb, placements)
        # rigorous solvability with special auto-clear (engine radius-1)
        if solve_v3_special(board, special_ids=sids, max_expansions=200_000)[0] is not True:
            continue
        if solve_v3_special(board, special_ids=sids, max_expansions=2_000_000)[0] is not True:
            continue
        if not _all_specials_covered(board, sids_set):
            continue
        cells = board.all_cells()
        n_normal = sum(1 for c in cells if c.tile_id not in sids_set)
        assert n_normal % 3 == 0, "normals not ÷3 — bug"
        # emit
        size_rng = random.Random(seed * 7 + 13)
        by = {}
        for c in cells:
            is_spec = c.tile_id in sids_set
            stone = {"i": (c.tile_id if is_spec else c.tile_id + 1), "x": c.x, "y": c.y}
            if is_spec:
                if a.size is not None:
                    stone["s"] = a.size
                elif c.tile_id == 1001:
                    stone["s"] = BONUS_SIZE
                else:
                    stone["s"] = _mission_size(size_rng)
            by.setdefault(c.layer_idx, []).append(stone)
        layers = [{"index": L, "stones": by[L]} for L in sorted(by)]
        names = {1001: "bonus", 1002: "mission"}
        kind = "_".join(names.get(s, str(s)) for s in sorted(reserve_spec))
        data = {"group": 1, "tiles": "", "layers": layers,
                "stacks": nb._stacks if hasattr(nb, "_stacks") else [],
                "metadata": {"source": f"reserve_{kind}",
                             "special_counts": {str(s): reserve_spec[s] for s in sorted(reserve_spec)},
                             "normal_tiles": n_normal, "normal_score": round(fs, 2),
                             "solvable_v3_special": True, "specials_covered_at_start": True,
                             "placement": "interstitial 2x2 centre (direction C)"}}
        out = a.out or a.layout.replace(".json", f"_{kind}.json").replace("NewLayout_", f"Level_{kind}_")
        json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
        print(f"-> {out}")
        print(f"   {kind}: added {reserve_spec} as interstitial 2×2 covers  | normals={n_normal} (÷3) "
              f"| score={fs:.1f}  | seed={seed}")
        print("   v3-solvable with special AUTO-CLEAR; every special COVERED at start (won't auto-clear immediately).")
        return 0

    if best_placed < n_special:
        print(f"could not host all {n_special} specials as covered 2×2 covers in {a.seeds} seeds "
              f"(best placed {best_placed}). Try fewer specials, a deeper layout, or more --seeds.")
    else:
        print(f"no v3-solvable placement found in {a.seeds} seeds — raise --seeds or adjust knobs.")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
