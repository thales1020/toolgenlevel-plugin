"""Add SPECIAL tiles (bonus 1001 / mission 1002) to a layout — the CORRECT way (direction C).

Reverse-engineered from the BonusLevel + MissionTile reference data:
  - The NORMAL tiles are a COMPLETE ÷3 match-3 set on their own (52/52 reference files: normal-count is
    ÷3). Specials are NOT reserved match-3 slots — they are ADDITIONAL cover stones sitting at their OWN
    interstitial positions, and they never consume a normal cell.
  - A special is a cover whose FOOTPRINT is a 2×2 (collision half 1.0, centre on a half-integer) OR a
    3×3 (half 1.5, centre on an integer) — encoded by the stone's `s` (mission 0.7=2×2/1.0=3×3, bonus
    1.0=2×2/1.5=3×3). It covers the tiles under its footprint and auto-clears once nothing covers IT.
    It need NOT fully cover the footprint (partial is fine) and must stay WITHIN the layout bounds.

Algorithm:
  1. Assign a full NORMAL match-3 level on the layout (all cells, trimmed to ÷3), verified v3-solvable.
  2. Renumber normals onto EVEN layers (layer_idx*2); place each special on the ODD layer between, at a
     2×2/3×3 centre whose footprint fits inside the layout, covers ≥1 tile below, and is still covered
     by a higher NORMAL at start (so it does NOT auto-clear immediately). No normal is removed (÷3 kept).
  3. Tag each special cell with `special_half` and verify on the FULL board with solve_v3_special
     (footprint-aware), assert every special is COVERED at start, assert normals ÷3.

These tiles are OPTIONAL — only run this when the design asks for bonus/mission tiles.

Usage:
  python reserve_special.py <empty_layout.json> --bonus N --mission M
       [--mission-cover 2x2|3x3] [--bonus-cover 2x2|3x3] [--size S]
       [--out o.json] [--color-count 10] [--distance 2] [--seeds 40] [--smin S --smax S]
  # legacy single-special form still works:  --id 1001|1002 --n N
"""
import sys, os, json, argparse, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
sys.path.insert(0, HERE)
from tile_level_simulator import load_board_from_file, TEEngine, DifficultyScorer, Board, Layer, Cell
from verify_smart_v3 import solve_v3, build_bitmask_visibility
from solve_special import solve_v3_special, footprint_half

WEIGHTS = json.load(open(os.path.join(os.path.dirname(HERE), "engine", "scoring_weights.json"), encoding="utf-8"))

# FOOTPRINT ⇄ render-size `s` (the stone's `s` encodes the special's coverage size):
#   2×2 (collision half 1.0, centre on a HALF-integer): mission s=0.7, bonus s=1.0
#   3×3 (collision half 1.5, centre on an INTEGER):      mission s=1.0, bonus s=1.5
# The player + solver read the footprint back from `s` via solve_special.footprint_half.
_COVER_HALF = {"2x2": 1.0, "3x3": 1.5}


def _emit_s(sid, half):
    """The render `s` to write for a special of this id + footprint half (inverse of footprint_half)."""
    big = half >= 1.5
    if sid == 1001:
        return 1.5 if big else 1.0
    return 1.0 if big else 0.7


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


def _bbox(cells):
    xs = [c.x for c in cells]; ys = [c.y for c in cells]
    return min(xs) - 0.5, max(xs) + 0.5, min(ys) - 0.5, max(ys) + 0.5   # cells are 1×1


def _find_placements(board, rng, half):
    """Candidate sites for a special of collision `half` (1.0 = 2×2, 1.5 = 3×3). Returns
    [(cov_above, cx, cy, L)]. Centres are drawn from a 0.5 GRID near the tiles — BOTH the neat cluster
    centres AND the ~½-cell-OFFSET (straddling) ones — and OFFSET positions are PREFERRED: a special
    shifted ~½ a cell straddles the grid so MANY normals each cover only ~half of it (it peeks out
    around them, like the real game) instead of sitting snug in one cluster.
    A site is valid iff: the whole footprint (centre ± half) lies WITHIN the layout bbox; it covers ≥1
    real tile below (partial cover OK); and ≥1 tile sits above it (covered at start → no immediate
    auto-clear). L = the interstitial layer (special goes on 2L+1). Ordered: highest layer (visible),
    then MOST straddle (offset), then fewest coverers."""
    cells = board.all_cells()
    x0, x1, y0, y1 = _bbox(cells)
    thr = half + 0.5                                  # a 1×1 cell is under the footprint iff |offset| < thr
    core = half - 0.5                                 # ...and FULLY under iff |offset| <= core (both axes)
    # 0.5-grid of candidate centres near the tiles: neat cluster centres + ½-cell-offset (straddle) ones
    centres = set()
    for c in cells:
        for dx in (-0.5, 0.0, 0.5):
            for dy in (-0.5, 0.0, 0.5):
                centres.add((round(c.x + dx, 4), round(c.y + dy, 4)))
    cand = []                                         # (straddle, above, cx, cy, L) — straddle/above sort keys
    for (cx, cy) in centres:
        if cx - half < x0 - 1e-9 or cx + half > x1 + 1e-9 or cy - half < y0 - 1e-9 or cy + half > y1 + 1e-9:
            continue                                  # footprint would stick out of the layout
        per_layer = {}
        straddle = 0                                  # cells only PARTIALLY under the footprint (offset → many)
        for c in cells:
            adx = abs(c.x - cx); ady = abs(c.y - cy)
            if adx < thr and ady < thr:
                per_layer[c.layer_idx] = per_layer.get(c.layer_idx, 0) + 1
                if adx > core + 1e-9 or ady > core + 1e-9:
                    straddle += 1                     # half-covered (centre in the outer band)
        if not per_layer:
            continue
        for L in sorted(per_layer, reverse=True):     # keep ALL valid interstitial L so specials can stack
            below = sum(n for l, n in per_layer.items() if l <= L)
            above = sum(n for l, n in per_layer.items() if l > L)
            if below >= 1 and above >= 1:
                cand.append((straddle, above, cx, cy, L))
    rng.shuffle(cand)
    cand.sort(key=lambda t: (-t[4], -t[0], t[1]))     # highest layer, then MOST straddle (offset), then fewest coverers
    return [(above, cx, cy, L) for (straddle, above, cx, cy, L) in cand]


def _build_with_specials(normal_board, placements):
    """placements: [(cx,cy,L,sid,half)]. New board: normals on EVEN layers (2*L), specials on ODD
    (2L+1). Returns (board, special_halves) where special_halves maps (round(x,4),round(y,4),layer)->half
    so the solver can apply each special's 2×2/3×3 footprint (Cell is __slots__-locked, can't be tagged)."""
    by = {}
    for c in normal_board.all_cells():
        by.setdefault(2 * c.layer_idx, []).append((c.x, c.y, c.tile_id))
    halves = {}
    for (cx, cy, L, sid, half) in placements:
        by.setdefault(2 * L + 1, []).append((cx, cy, sid))
        halves[(round(cx, 4), round(cy, 4), 2 * L + 1)] = half
    b = Board("special")
    for L in sorted(by):
        ly = Layer(L)
        for (x, y, t) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = t; ly.cells.append(cc)
        b.layers.append(ly)
    return b, halves


def _all_specials_covered(board, sids, halves):
    """Every special is COVERED at start by ANY higher-layer tile overlapping its footprint — a NORMAL
    OR a higher SPECIAL (a lower special in an overlapping stack is validly covered by the one above it;
    the TOP of each stack still needs a normal, since nothing special sits above it). So no special
    auto-clears at level start. Matches player + solver (which count special-on-special coverage)."""
    cells = board.all_cells()

    def _half(c):
        return halves.get((round(c.x, 4), round(c.y, 4), c.layer_idx), 1.0) if c.tile_id in sids else 0.5

    for sc in cells:
        if sc.tile_id in sids:
            hs = _half(sc)
            if not any(c is not sc and c.layer_idx > sc.layer_idx
                       and abs(c.x - sc.x) < hs + _half(c) and abs(c.y - sc.y) < hs + _half(c)
                       for c in cells):
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
                    help="render size 's' OVERRIDE for ALL specials (else derived from the cover footprint: "
                         "mission 2x2=0.7/3x3=1.0, bonus 2x2=1.0/3x3=1.5). s ALSO encodes the footprint.")
    ap.add_argument("--mission-cover", choices=("2x2", "3x3"), default="2x2", help="footprint for --mission N (default 2x2)")
    ap.add_argument("--bonus-cover", choices=("2x2", "3x3"), default="2x2", help="footprint for --bonus N (default 2x2)")
    # explicit per-footprint counts — MIX 2x2 and 3x3 specials in one level (add on top of --mission/--bonus)
    ap.add_argument("--mission-2x2", type=int, default=0, help="mission tiles with a 2x2 footprint (s=0.7)")
    ap.add_argument("--mission-3x3", type=int, default=0, help="mission tiles with a 3x3 footprint (s=1.0)")
    ap.add_argument("--bonus-2x2", type=int, default=0, help="bonus tiles with a 2x2 footprint (s=1.0)")
    ap.add_argument("--bonus-3x3", type=int, default=0, help="bonus tiles with a 3x3 footprint (s=1.5)")
    ap.add_argument("--color-count", type=int, default=10)
    ap.add_argument("--distance", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=40, help="seeds to try")
    ap.add_argument("--smin", type=float, default=None, help="optional min normal-board final_score")
    ap.add_argument("--smax", type=float, default=None, help="optional max normal-board final_score")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    # `want` = one (sid, footprint-half) per special to place. Supports MIXING 2×2 and 3×3.
    H = _COVER_HALF
    want = []
    if a.mission: want += [(1002, H[a.mission_cover])] * a.mission
    if a.bonus:   want += [(1001, H[a.bonus_cover])]   * a.bonus
    want += [(1002, H["2x2"])] * a.mission_2x2 + [(1002, H["3x3"])] * a.mission_3x3
    want += [(1001, H["2x2"])] * a.bonus_2x2   + [(1001, H["3x3"])] * a.bonus_3x3
    if a.id is not None:
        if a.n is None:
            raise SystemExit("--id requires --n")
        cov = a.bonus_cover if a.id == 1001 else a.mission_cover
        want += [(a.id, H[cov])] * a.n
    if not want:
        raise SystemExit("specify --mission/--bonus (+ --*-cover) or --mission-2x2/--mission-3x3/--bonus-2x2/--bonus-3x3")
    reserve_spec = {}
    for (sid, _) in want:
        reserve_spec[sid] = reserve_spec.get(sid, 0) + 1
    sids = tuple(sorted(reserve_spec))
    sids_set = set(sids)
    n_special = len(want)
    halves_needed = sorted(set(h for (_, h) in want))

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
        cand_by_half = {h: _find_placements(nb, rng, h) for h in halves_needed}
        # assign each wanted special a site; chosen footprints must not overlap each other
        chosen = []                         # (cx, cy, L, half)
        used = set()                        # exact (cx,cy,L) already taken
        for (sid, half) in want:
            got = None
            for (cov, cx, cy, L) in cand_by_half[half]:
                if (cx, cy, L) in used:
                    continue                # not the identical site
                # overlap IS allowed, but two OVERLAPPING specials must NOT share the final layer (2L+1),
                # else neither covers the other and a lower one auto-clears while the other sits on it.
                # Force overlapping specials onto DISTINCT layers -> a clear higher/lower cover relationship.
                if any(pL == L and abs(cx - px) < (half + ph) and abs(cy - py) < (half + ph)
                       for (px, py, pL, ph) in chosen):
                    continue
                got = (cx, cy, L, half); break
            if got is None:
                break
            used.add((got[0], got[1], got[2]))
            chosen.append(got)
        best_placed = max(best_placed, len(chosen))
        if len(chosen) < n_special:
            continue                       # this seed can't host them all — try another
        placements = [(cx, cy, L, sid, half)
                      for (cx, cy, L, half), (sid, _) in zip(chosen, want)]
        board, sh_map = _build_with_specials(nb, placements)
        # rigorous solvability with special auto-clear + per-special 2×2/3×3 footprint
        if solve_v3_special(board, special_ids=sids, max_expansions=200_000, special_halves=sh_map)[0] is not True:
            continue
        if solve_v3_special(board, special_ids=sids, max_expansions=2_000_000, special_halves=sh_map)[0] is not True:
            continue
        if not _all_specials_covered(board, sids_set, sh_map):
            continue
        cells = board.all_cells()
        n_normal = sum(1 for c in cells if c.tile_id not in sids_set)
        assert n_normal % 3 == 0, "normals not ÷3 — bug"
        # emit — a special's `s` encodes its footprint (2×2/3×3); --size overrides
        by = {}
        for c in cells:
            is_spec = c.tile_id in sids_set
            stone = {"i": (c.tile_id if is_spec else c.tile_id + 1), "x": c.x, "y": c.y}
            if is_spec:
                h = sh_map.get((round(c.x, 4), round(c.y, 4), c.layer_idx), 1.0)
                stone["s"] = a.size if a.size is not None else _emit_s(c.tile_id, h)
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
                             "placement": f"interstitial covers (direction C); bonus={a.bonus_cover} mission={a.mission_cover}"}}
        out = a.out or a.layout.replace(".json", f"_{kind}.json").replace("NewLayout_", f"Level_{kind}_")
        json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
        print(f"-> {out}")
        print(f"   {kind}: added {reserve_spec} as interstitial covers "
              f"(bonus={a.bonus_cover}, mission={a.mission_cover})  | normals={n_normal} (÷3) "
              f"| score={fs:.1f}  | seed={seed}")
        print("   v3-solvable with special AUTO-CLEAR; every special COVERED at start (won't auto-clear immediately).")
        return 0

    if best_placed < n_special:
        print(f"could not host all {n_special} specials as covered footprints in {a.seeds} seeds "
              f"(best placed {best_placed}). Try fewer specials, 2x2 instead of 3x3, a deeper/bigger "
              f"layout, or more --seeds.")
    else:
        print(f"no v3-solvable placement found in {a.seeds} seeds — raise --seeds or adjust knobs.")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
