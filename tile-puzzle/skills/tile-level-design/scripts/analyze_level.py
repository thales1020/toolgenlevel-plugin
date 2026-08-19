"""Reverse-engineer level info from a saved stones-format JSON.

Computes:
  - Score (difficulty) via DifficultyScorer
  - Layer count
  - Distinct tile types
  - Total tile count
  - Layout name (match position pattern against sample_levels/)

Usage:
    python analyze_level.py <path-to-level.json> [--save]

If --save is passed, a "metadata" block is injected into the JSON file in-place
(extra top-level fields are ignored by the game loader, safe to ship).
"""
import sys, os, json

# Locate tile_level_simulator.py — skill is self-contained (engine/ next to scripts/).
_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_ROOT = os.path.dirname(_HERE)              # .../tile-level-design
_CANDIDATES = [
    os.path.join(_SKILL_ROOT, "engine"),          # canonical: skill/engine
    _HERE,
    "c:/Users/PC1150/Downloads/GD_Test",          # legacy fallback
]
for _d in _CANDIDATES:
    if os.path.isfile(os.path.join(_d, "tile_level_simulator.py")):
        sys.path.insert(0, _d)
        _PROJECT_DIR = _d
        break
else:
    raise ModuleNotFoundError(
        "tile_level_simulator.py not found in any of: " + ", ".join(_CANDIDATES)
    )

sys.path.insert(0, _HERE)  # so sibling scripts (gen_pattern, solve_dispatch) import cleanly regardless of caller cwd
from tile_level_simulator import load_board_from_file, DifficultyScorer, load_scoring_weights
from diff_score import compute_new_diffscore, tier as _diff_tier   # validated player-difficulty formula


def position_signature(data):
    """Build a hashable signature of (layer_idx, x, y) positions only — ignores tile_id."""
    sig = []
    for layer in sorted(data["layers"], key=lambda l: l["index"]):
        for s in layer["stones"]:
            sig.append((layer["index"], round(s["x"], 2), round(s["y"], 2)))
    return tuple(sorted(sig))


def assert_geometry_unchanged(before_data, after_data, context=""):
    """Guard against a layout's cell set silently drifting (Task 1: a script that was supposed to only
    ASSIGN TILES must not turn Layout_A into a de-facto Layout_A1 by adding/dropping cells). Both args
    are stones-format dicts (same shape `position_signature` reads: {"layers":[{"index","stones":[...]}]}).
    Raises loudly on mismatch -- callers that legitimately change geometry (add_stacks.py pre-tile,
    reserve_special.py's special-cell overlay) must not call this, or must call it only across the
    step where they DON'T expect a change."""
    before_sig = position_signature(before_data)
    after_sig = position_signature(after_data)
    if before_sig != after_sig:
        raise SystemExit(
            f"geometry changed unexpectedly during '{context}' -- "
            f"{len(before_sig)} cells before, {len(after_sig)} cells after. "
            f"This must be an explicit, documented step (see SKILL.md sec.22b, "
            f"'Geometry is immutable during tile assignment'), "
            f"never a side effect.")


def detect_layout(target_path, samples_dir=None):
    """Match position pattern against sample layouts."""
    if samples_dir is None:
        for d in (os.path.join(_SKILL_ROOT, "sample_layouts"),
                  os.path.join(_PROJECT_DIR, "sample_levels")):
            if os.path.isdir(d):
                samples_dir = d
                break
    samples_dir = os.path.abspath(samples_dir) if samples_dir else None
    with open(target_path, encoding="utf-8") as f:
        target_data = json.load(f)
    target_sig = position_signature(target_data)

    matches = []
    if not samples_dir or not os.path.isdir(samples_dir):
        return matches
    for fname in os.listdir(samples_dir):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(samples_dir, fname), encoding="utf-8") as f:
            sample_data = json.load(f)
        if "layers" not in sample_data:
            continue
        if position_signature(sample_data) == target_sig:
            matches.append(fname)
    return matches


def _classify_solve_profile(dfs_solvable, fail_rate):
    """Task 4 classification rule. Reuses the SAME 0.90/0.80-ish thresholds already established by the
    'trap an' pattern (reference/hidden_trap_levels.md) -- nothing new invented. See
    reference/greedy_vs_exact.md for the full mechanism decision table. NOT a difficulty ranking rule --
    orthogonal to new_diffScore (does the obvious path diverge from the necessary path, not how hard)."""
    if not dfs_solvable:
        return "unsolvable"          # should never ship; useful when debugging a rejected candidate
    if fail_rate is None:
        return None                  # board has specials -- playout()'s model doesn't apply
    if fail_rate >= 0.90:
        return "hidden_trap"
    if fail_rate < 0.20:
        return "straightforward"
    return "partial_trap"


def compute_solve_profile(board, runs=300):
    """Run BOTH exact solving (via solve_dispatch.solve_any, so specials are handled correctly) and
    (for normal boards only) gen_pattern's greedy-playout evaluator, and classify the result. This is
    the ONLY place in the pipeline these two are combined into one persisted, labeled conclusion
    (SKILL.md sec.3.4). OFF by default -- callers opt in (--solve-profile) since 300 playouts is real
    cost not worth paying on the common analyze_level.py path."""
    from solve_dispatch import solve_any
    status, _depth, _exp = solve_any(board, max_expansions=500_000)
    dfs_solvable = status is True
    cells = board.all_cells()
    has_special = any(c.tile_id >= 1000 for c in cells)
    fail_rate = None
    if dfs_solvable and not has_special:
        from verify_smart_v3 import build_bitmask_visibility
        from gen_pattern import playout
        blocked_by, _blocks = build_bitmask_visibility(cells)
        tile_ids = [c.tile_id for c in cells]
        fail_rate, _avg_cleared = playout(tile_ids, blocked_by, len(cells), mode="greedy", runs=runs)
        fail_rate = round(fail_rate, 3)
    return {
        "dfs_solvable": dfs_solvable,
        "greedy_fail_rate": fail_rate,
        "greedy_runs": runs if fail_rate is not None else None,
        "classification": _classify_solve_profile(dfs_solvable, fail_rate),
    }


def compute_metadata(path, solve_profile=False):
    """Compute level metadata. Returns (metadata_dict, raw_data)."""
    path = os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    n_layers = len(data["layers"])
    total_tiles = sum(len(l["stones"]) for l in data["layers"])

    type_counts = {}
    for layer in data["layers"]:
        for s in layer["stones"]:
            tid = s.get("i", 0)
            type_counts[tid] = type_counts.get(tid, 0) + 1
    distinct_types = sorted(type_counts.keys())
    n_types = len(distinct_types)

    board = load_board_from_file(path)
    score_obj = None
    new_diff = None                       # validated player-difficulty (new_diffScore)
    if board is not None:
        weights = load_scoring_weights()
        score_obj = DifficultyScorer.compute_full_score(board, weights=weights)
        is_mystery = 1 if any(s.get("m") for ly in data["layers"] for s in ly.get("stones", [])) else 0
        nd, _s, _nt = compute_new_diffscore(board, weights, is_mystery)
        new_diff = {"new_diffscore": round(nd, 2), "tier": _diff_tier(nd), "is_mystery": is_mystery}

    layout_matches = detect_layout(path)
    layout_name = layout_matches[0].replace("NewLayout_", "").replace(".json", "") \
        if layout_matches else None

    metadata = {
        "layout": layout_name,
        "n_layers": n_layers,
        "n_types": n_types,
        "total_tiles": total_tiles,
        # RECOMMENDED difficulty rank (real-play validated). `difficulty` below is the OLD chaos-score.
        "new_diffscore": new_diff["new_diffscore"] if new_diff else None,
        "difficulty_tier": new_diff["tier"] if new_diff else None,
        "difficulty": round(score_obj["final_score"], 2) if score_obj else None,
        "score_components": {
            "layout": round(score_obj["layout"], 2),
            "inter_group": round(score_obj["inter_group"], 2),
            "intra_group": round(score_obj["intra_group"], 2),
            "cover100": score_obj["cover100"],
            "pickable_diversity": score_obj["pickable_diversity"],
        } if score_obj else None,
        "type_distribution": dict(sorted(type_counts.items())),
    }
    if solve_profile and board is not None:
        metadata["solve_profile"] = compute_solve_profile(board)
    return metadata, data


def analyze(path, save=False, solve_profile=False):
    metadata, data = compute_metadata(path, solve_profile=solve_profile)

    print(f"File: {os.path.abspath(path)}")
    print(f"  Layout:          {metadata['layout']}")
    print(f"  So layer:        {metadata['n_layers']}")
    print(f"  So tile total:   {metadata['total_tiles']}")
    print(f"  So loai tile:    {metadata['n_types']}")
    _nt = metadata["n_types"]
    if not (8 <= _nt <= 22):
        print(f"  [!] n_types={_nt} ngoai khoang 8-22 cho phep (SKILL.md, khuyen nghi 10-20, "
              f"+-2 cho do kho cuc doan) -- xem lai yeu cau do kho thay vi day tiep n_types.")
    elif not (10 <= _nt <= 20):
        print(f"  [i] n_types={_nt} ngoai khoang khuyen nghi 10-20 (van trong bien +-2 cho do kho cuc doan).")
    if metadata.get("new_diffscore") is not None:
        print(f"  Do kho (new_diffScore): {metadata['new_diffscore']}  [{metadata['difficulty_tier']}]"
              f"   <- RANK levels with THIS (real-play validated)")
    if metadata["difficulty"] is not None:
        c = metadata["score_components"]
        print(f"  final_score (OLD chaos, visual complexity — NOT player-difficulty): {metadata['difficulty']}")
        print(f"    layout={c['layout']} inter={c['inter_group']} intra={c['intra_group']} "
              f"cover100={c['cover100']} pickdiv={c['pickable_diversity']}")
    print(f"  Type distribution: {metadata['type_distribution']}")
    if metadata.get("solve_profile") is not None:
        sp = metadata["solve_profile"]
        gfr = f"{sp['greedy_fail_rate']*100:.0f}%" if sp['greedy_fail_rate'] is not None else "N/A (has specials)"
        print(f"  Solve profile: dfs_solvable={sp['dfs_solvable']}  greedy_fail_rate={gfr}  "
              f"classification={sp['classification']}  (NOT a difficulty rank -- see new_diffscore above)")

    if save:
        data["metadata"] = metadata
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        print(f"\nMetadata saved into {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_level.py <path-to-level.json> [--save] [--solve-profile]")
        sys.exit(1)
    save_flag = "--save" in sys.argv
    solve_profile_flag = "--solve-profile" in sys.argv
    target = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    analyze(target, save=save_flag, solve_profile=solve_profile_flag)
