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

Solvability: v3 is checked on the MATCH-3 tiles (the special cells are removed for the solve — they
auto-clear for free when exposed, so the match-3 board is the real game). This guarantees the playable
(match-3) part is ÷3-balanced and clearable.

These tiles are OPTIONAL — only run this when the design asks for bonus/mission tiles.

Usage:
  python reserve_special.py <empty_layout.json> --id 1001 --n 4 [--size 0.7]
       [--out o.json] [--color-count 10] [--distance 2] [--seeds 30] [--smin S --smax S]
"""
import sys, os, json, argparse, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
from tile_level_simulator import load_board_from_file, TEEngine, DifficultyScorer, Board, Layer, Cell
from verify_smart_v3 import solve_v3

WEIGHTS = json.load(open(os.path.join(os.path.dirname(HERE), "engine", "scoring_weights.json"), encoding="utf-8"))


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
    ap.add_argument("--id", type=int, required=True, help="special tile id: 1001 bonus / 1002 mission")
    ap.add_argument("--n", type=int, required=True, help="how many special tiles to reserve")
    ap.add_argument("--size", type=float, default=None,
                    help="optional render size 's' for the special tiles (omit = game default; the round "
                         "shape comes from the id 1001/1002, NOT from s — s only rescales)")
    ap.add_argument("--color-count", type=int, default=10)
    ap.add_argument("--distance", type=int, default=2)
    ap.add_argument("--seeds", type=int, default=40, help="seeds to try for a v3-solvable match-3")
    ap.add_argument("--smin", type=float, default=None, help="optional min final_score")
    ap.add_argument("--smax", type=float, default=None, help="optional max final_score")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    special_ids = {a.id}

    for seed in range(1, a.seeds + 1):
        random.seed(seed)
        board = load_board_from_file(a.layout)
        board.clear_tiles()
        cells = board.all_cells()
        total = len(cells)
        if a.n >= total:
            raise SystemExit("--n too large for this layout")
        # 1. reserve N random cells as the special id; the REST are the match-3 cells
        reserved = set(id(c) for c in random.sample(cells, a.n))
        for c in cells:
            c.tile_id = a.id if id(c) in reserved else -1
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
        # 4. verify v3 on the MATCH-3 board (specials excluded; they auto-clear for free on exposure)
        m3 = _match3_board(board, special_ids)
        if solve_v3(m3, 200_000)[0] is not True:
            continue
        if solve_v3(m3, 2_000_000)[0] is not True:
            continue
        # optional score band (scored on the match-3 board)
        sc = DifficultyScorer.compute_full_score(m3, WEIGHTS); fs = sc["final_score"]
        if (a.smin is not None and fs < a.smin) or (a.smax is not None and fs > a.smax):
            continue
        # 5. emit level: specials get size s; everything else is match-3
        by = {}
        for c in board.all_cells():
            stone = {"i": (c.tile_id if c.tile_id in special_ids else c.tile_id + 1), "x": c.x, "y": c.y}
            if c.tile_id in special_ids and a.size is not None:
                stone["s"] = a.size
            by.setdefault(c.layer_idx, []).append(stone)
        layers = [{"index": L, "stones": by[L]} for L in sorted(by)]
        kind = {1001: "bonus", 1002: "mission"}.get(a.id, "special")
        data = {"group": 1, "tiles": "", "layers": layers, "stacks": board._stacks if hasattr(board, "_stacks") else [],
                "metadata": {"source": f"reserve_{kind}", "special_id": a.id, "special_count": a.n,
                             "match3_tiles": total - a.n - len(dropped), "match3_score": round(fs, 2),
                             "match3_solvable_v3": True}}
        out = a.out or a.layout.replace(".json", f"_{kind}.json").replace("NewLayout_", f"Level_{kind}_")
        json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
        print(f"-> {out}")
        print(f"   {kind} id={a.id}: reserved {a.n}  | match-3 tiles={total - a.n - len(dropped)} "
              f"(÷3, v3-solvable, score={fs:.1f})  | trimmed {len(dropped)} for %3  | seed={seed}")
        print("   special tiles auto-clear on exposure; v3 verified on the match-3 board.")
        return 0
    print(f"no v3-solvable match-3 found in {a.seeds} seeds — raise --seeds or adjust knobs.")
    return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
