"""new_diffScore — the VALIDATED player-difficulty formula (use THIS to rank levels).

Fit + validated on ~55K real plays of the live Pyramid game (docs/HANDOFF_KNOWLEDGE.md §4.3;
LOO-CV Spearman 0.615 over 120 levels, 0.732 on plain-only). It is a STATIC board formula:

    new_diffScore = max(0, -28.42 + 0.655*intra_group + 0.804*cover100 + 2.897*n_types + 22.76*is_mystery)

Inputs:
  - intra_group, cover100 : DifficultyScorer.compute_full_score(board, weights)   (the OLD chaos-score's
    two components that actually track difficulty — they feed THIS, don't rank with final_score).
  - n_types               : number of distinct tile_id over all cells.
  - is_mystery            : 1 if any stone is a Mystery Tile — new `o:[0]` or legacy `m:true`, else 0.

Known limitation (single dominant error): STATIC-only, BLIND to in-level mechanics — it always
UNDER-rates hard mechanic levels (never over-rates) EXCEPT the +22.76 mystery term, which OVER-rates
already-easy mystery boards. Practical ceiling for a board-only model ≈ 0.63–0.66; beyond needs
in-game mechanic simulation. Treat the tier labels as a RELATIVE guide, not gospel.

Usage:  python diff_score.py <level.json>
"""
import sys, os, json

# Locate the engine — skill is self-contained (engine/ next to scripts/); mirror analyze_level.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_HERE)
for _d in (os.path.join(_SKILL_ROOT, "engine"), _HERE):
    if os.path.isfile(os.path.join(_d, "tile_level_simulator.py")):
        sys.path.insert(0, _d)
        break
else:
    raise ModuleNotFoundError("tile_level_simulator.py not found next to scripts/ (engine/)")

from tile_level_simulator import load_board_from_file, DifficultyScorer, load_scoring_weights

# Coefficients — do NOT edit without a re-fit against the real-play ground truth (HANDOFF §4.3).
_C0, _C_INTRA, _C_COVER, _C_NTYPES, _C_MYSTERY = -28.42, 0.655, 0.804, 2.897, 22.76


def compute_new_diffscore(board, weights, is_mystery):
    """The validated formula. Returns a float clamped at >= 0."""
    s = DifficultyScorer.compute_full_score(board, weights=weights)
    n_types = len({c.tile_id for c in board.all_cells()})
    val = (_C0 + _C_INTRA * s["intra_group"] + _C_COVER * s["cover100"]
           + _C_NTYPES * n_types + _C_MYSTERY * (1 if is_mystery else 0))
    return max(0.0, val), s, n_types


def tier(score):
    """Approximate difficulty tier (a RELATIVE guide, calibrated from HANDOFF §5.1's ratio table)."""
    if score < 20:
        return "Easy"
    if score < 35:
        return "Normal"
    if score < 50:
        return "Hard"
    if score < 65:
        return "Very Hard"
    return "Extreme"


def _is_mystery_from_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    # mystery marker = new o:[0] OR legacy m:true (cloud is o:[1] — NOT mystery)
    return 1 if any(st.get("m") or (0 in (st.get("o") or []))
                    for ly in data.get("layers", []) for st in ly.get("stones", [])) else 0


def new_diffscore_for_file(path):
    """Load a level file (ABSOLUTE path required) and return the full new_diffScore breakdown."""
    path = os.path.abspath(path)
    board = load_board_from_file(path)
    if board is None:
        raise ValueError(f"could not load board from {path} (needs a valid stones-format level; "
                         "load_board_from_file also returns None on relative paths on Windows)")
    is_mystery = _is_mystery_from_json(path)
    weights = load_scoring_weights()
    score, s, n_types = compute_new_diffscore(board, weights, is_mystery)
    return {
        "new_diffscore": round(score, 2),
        "tier": tier(score),
        "intra_group": round(s["intra_group"], 2),
        "cover100": s["cover100"],
        "n_types": n_types,
        "is_mystery": is_mystery,
        "old_final_score": round(s["final_score"], 2),   # chaos-score: a feature, NOT for ranking
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python diff_score.py <level.json>")
        sys.exit(1)
    path = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    r = new_diffscore_for_file(path)
    print(f"File: {os.path.abspath(path)}")
    print(f"  new_diffScore : {r['new_diffscore']}   [{r['tier']}]   <- RANK levels with this")
    print(f"    intra_group={r['intra_group']}  cover100={r['cover100']}  "
          f"n_types={r['n_types']}  is_mystery={r['is_mystery']}")
    print(f"  old final_score (chaos, NOT for ranking): {r['old_final_score']}")


if __name__ == "__main__":
    main()
