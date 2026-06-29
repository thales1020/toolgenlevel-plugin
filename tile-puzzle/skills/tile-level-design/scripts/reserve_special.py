"""Reserve SPECIAL tiles (bonus 1001 / mission 1002) on an empty layout, then assign match-3 to the
REST — the correct way to add these OPTIONAL tiles (only when requested).

Reverse-engineered rule (BonusLevel + MissionTile reference data): the special ids 1001 (bonus, round)
and 1002 (mission) are NOT match-3 tiles — they sit in RESERVED slots and AUTO-CLEAR when uncovered.
Proof: `total - count(special)` is ÷3 in 100% of the reference files (the match-3 pool EXCLUDES the
special slots). So you must reserve the slots BEFORE assigning match-3, not retype a finished level
(that would unbalance a match-3 type and break solvability).

How: the engine's binder SKIPS any cell whose tile_id is already >=0 (`_bind_random`: "Pre-assigned
(HardBgTile) -> skip cell, DON'T consume pool"). So we pre-set N cells to the special id, set the rest
to -1, and TEEngine.generate fills only the rest with match-3. We trim the match-3 remainder to ÷3,
loop seeds for a v3-solvable match-3, then attach the special tiles' render size `s`.

Solvability: v3 (RIGOROUS) is checked on the FULL board via solve_special.solve_v3_special — the
special cells STAY as covers and auto-clear only when exposed, so the forced order they impose is
accounted for. (0.3.0 used a shortcut that excluded specials from the solve; 0.3.1 keeps them.)

These tiles are OPTIONAL — only run this when the design asks for bonus/mission tiles.

Usage:
  python reserve_special.py <empty_layout.json> --id 1001 --n 4 [--size 0.7]
       [--out o.json] [--color-count 10] [--distance 2] [--seeds 30] [--smin S --smax S]
"""
import sys, os, json, argparse, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
sys.path.insert(0, HERE)
from tile_level_simulator import load_board_from_file, TEEngine, DifficultyScorer, Board, Layer, Cell
from solve_special import solve_v3_special

WEIGHTS = json.load(open(os.path.join(os.path.dirname(HERE), "engine", "scoring_weights.json"), encoding="utf-8"))

# Render size 's' (cosmetic — the solver ignores it). Reverse-engineered from the reference sets:
#   BONUS (1001): always 1.5 (or absent). Fixed.
#   MISSION (1002): VARIED. Early/mid levels (L30-120) "mix" a small base with an occasional larger
#     accent within ONE level: base 0.6 (sometimes 0.55), accents 0.9 (common), 1.2/0.95 (rare). Late
#     levels (L130-300) are uniform 0.7. Default here = the L30-120 MIXED style (per-tile weighted).
BONUS_SIZE = 1.5
# (value, weight) reproducing the L30-120 mission size distribution
_MISSION_SIZE_DIST = [(0.6, 60), (0.55, 13), (0.9, 19), (0.95, 3), (1.2, 5)]


def _mission_size(rng):
    """Sample one mission render size in the L30-120 'mixed' style (base 0.6 + occasional larger)."""
    total = sum(w for _, w in _MISSION_SIZE_DIST)
    r = rng.uniform(0, total)
    acc = 0
    for v, w in _MISSION_SIZE_DIST:
        acc += w
        if r < acc:
            return v
    return _MISSION_SIZE_DIST[0][0]


def _match3_board(board, special_ids):
    """A board with the special cells removed — the match-3 game (specials auto-clear for free)."""
    b = Board("m3"); by = {}
    for c in board.all_cells():
        if c.tile_id in special_ids:
            continue
        by.setdefault(c.layer_idx, []).append((c.x, c.y, c.tile_id))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y, t) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = t; ly.cells.append(cc)
        b.layers.append(ly)
    return b


def _exposed_nospecial(board, special_ids):
    """Cells with nothing above them and not a special — safe to drop for the %3 trim."""
    cells = board.all_cells()
    out = []
    for c in cells:
        if c.tile_id in special_ids:
            continue
        covered = any(o.layer_idx > c.layer_idx and abs(o.x - c.x) < 1 and abs(o.y - c.y) < 1 for o in cells)
        if not covered:
            out.append(c)
    return out


def main():
    ap = argparse.ArgumentParser(description="Reserve bonus/mission special tiles + assign match-3 to the rest.")
    ap.add_argument("layout", help="EMPTY layout JSON (no tiles)")
    # single-special (back-compat) OR combine bonus + mission in ONE level via --bonus/--mission
    ap.add_argument("--id", type=int, default=None, help="single special id: 1001 bonus / 1002 mission")
    ap.add_argument("--n", type=int, default=None, help="count for --id")
    ap.add_argument("--bonus", type=int, default=0, help="how many BONUS (1001) tiles to reserve")
    ap.add_argument("--mission", type=int, default=0, help="how many MISSION (1002) tiles to reserve")
    ap.add_argument("--size", type=float, default=None,
                    help="optional render size 's' OVERRIDE for ALL specials. Omit = reference defaults: "
                         "bonus 1.5 (fixed), mission per-tile MIXED sample (base 0.6 + occasional 0.9/1.2, "
                         "the L30-120 style). s is cosmetic — the round shape comes from the id, not s.")
    ap.add_argument("--color-count", type=int, default=10)
    ap.add_argument("--distance", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=40, help="seeds to try for a v3-solvable match-3")
    ap.add_argument("--smin", type=float, default=None, help="optional min final_score")
    ap.add_argument("--smax", type=float, default=None, help="optional max final_score")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    # build {special_id: count} from either the single --id/--n or the --bonus/--mission combo
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
    special_ids = set(reserve_spec)
    n_special = sum(reserve_spec.values())

    for seed in range(1, a.seeds + 1):
        random.seed(seed)
        board = load_board_from_file(a.layout)
        board.clear_tiles()
        cells = board.all_cells()
        total = len(cells)
        if n_special >= total:
            raise SystemExit("reserved count too large for this layout")
        # 1. reserve cells for EACH special id; the REST are the match-3 cells
        picked = random.sample(cells, n_special)
        reserved = {}            # id(cell) -> special tile id
        i = 0
        for sid, cnt in reserve_spec.items():
            for c in picked[i:i + cnt]:
                reserved[id(c)] = sid
            i += cnt
        for c in cells:
            c.tile_id = reserved.get(id(c), -1)
        match3_cells = [c for c in cells if id(c) not in reserved]
        # 2. trim match-3 remainder to %3 by dropping exposed match-3 cells (keep specials)
        rem = len(match3_cells) % 3
        dropped = []
        if rem:
            ex = [c for c in _exposed_nospecial(board, special_ids) if id(c) not in reserved]
            random.shuffle(ex)
            dropped = ex[:rem]
            drop_ids = set(id(c) for c in dropped)
            for ly in board.layers:
                ly.cells = [c for c in ly.cells if id(c) not in drop_ids]
            match3_cells = [c for c in match3_cells if id(c) not in drop_ids]
        # 3. bind match-3 ONLY to the match-3 cells (specials left as-is; _fix_x3 sees only match-3)
        eng = TEEngine(); eng.validate = False
        eng.color_count = a.color_count; eng.hard_code = 0; eng.distance = a.distance
        eff_cc = eng._get_effective_cc()
        pool = eng._build_icon_pool(len(match3_cells), eff_cc)
        flags = eng._compute_knob_flags(board, eff_cc)
        eng._bind_random(match3_cells, pool, eff_cc, flags)
        eng._fix_x3_distribution(match3_cells, eff_cc)
        # 4. verify v3 with special AUTO-CLEAR on the FULL board — RIGOROUS: the specials stay in the
        #    board as covers (they auto-clear only when exposed), so the forced-order they impose is
        #    accounted for (not the 0.3.0 shortcut that excluded them).
        sids = tuple(special_ids)
        if solve_v3_special(board, special_ids=sids, max_expansions=200_000)[0] is not True:
            continue
        if solve_v3_special(board, special_ids=sids, max_expansions=2_000_000)[0] is not True:
            continue
        m3 = _match3_board(board, special_ids)          # score the match-3 difficulty on the match-3 set
        # optional score band (scored on the match-3 board)
        sc = DifficultyScorer.compute_full_score(m3, WEIGHTS); fs = sc["final_score"]
        if (a.smin is not None and fs < a.smin) or (a.smax is not None and fs > a.smax):
            continue
        # 5. emit level: specials get render size s; rest is match-3.
        #    bonus -> fixed 1.5; mission -> L30-120 'mixed' per-tile sample; --size overrides ALL.
        size_rng = random.Random(seed * 7 + 13)      # deterministic per winning seed
        by = {}
        for c in board.all_cells():
            is_spec = c.tile_id in special_ids
            stone = {"i": (c.tile_id if is_spec else c.tile_id + 1), "x": c.x, "y": c.y}
            if is_spec:
                if a.size is not None:
                    stone["s"] = a.size
                elif c.tile_id == 1001:
                    stone["s"] = BONUS_SIZE
                elif c.tile_id == 1002:
                    stone["s"] = _mission_size(size_rng)
                else:
                    stone["s"] = 1.0
            by.setdefault(c.layer_idx, []).append(stone)
        layers = [{"index": L, "stones": by[L]} for L in sorted(by)]
        names = {1001: "bonus", 1002: "mission"}
        kind = "_".join(names.get(s, str(s)) for s in sorted(reserve_spec))
        data = {"group": 1, "tiles": "", "layers": layers, "stacks": board._stacks if hasattr(board, "_stacks") else [],
                "metadata": {"source": f"reserve_{kind}",
                             "special_counts": {str(s): reserve_spec[s] for s in sorted(reserve_spec)},
                             "match3_tiles": total - n_special - len(dropped), "match3_score": round(fs, 2),
                             "match3_solvable_v3": True}}
        out = a.out or a.layout.replace(".json", f"_{kind}.json").replace("NewLayout_", f"Level_{kind}_")
        json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
        print(f"-> {out}")
        print(f"   {kind}: reserved {reserve_spec}  | match-3 tiles={total - n_special - len(dropped)} "
              f"(÷3, v3-solvable, score={fs:.1f})  | trimmed {len(dropped)} for %3  | seed={seed}")
        print("   v3 verified on the FULL board with special AUTO-CLEAR (specials kept as covers).")
        return 0
    print(f"no v3-solvable match-3 found in {a.seeds} seeds — raise --seeds or adjust knobs.")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
