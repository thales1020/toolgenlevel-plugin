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

from tile_level_simulator import load_board_from_file, DifficultyScorer, load_scoring_weights
from diff_score import compute_new_diffscore, tier as _diff_tier   # validated player-difficulty formula


def position_signature(data):
    """Build a hashable signature of (layer_idx, x, y) positions only — ignores tile_id."""
    sig = []
    for layer in sorted(data["layers"], key=lambda l: l["index"]):
        for s in layer["stones"]:
            sig.append((layer["index"], round(s["x"], 2), round(s["y"], 2)))
    return tuple(sorted(sig))


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


def compute_metadata(path):
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
    return metadata, data


def analyze(path, save=False):
    metadata, data = compute_metadata(path)

    print(f"File: {os.path.abspath(path)}")
    print(f"  Layout:          {metadata['layout']}")
    print(f"  So layer:        {metadata['n_layers']}")
    print(f"  So tile total:   {metadata['total_tiles']}")
    print(f"  So loai tile:    {metadata['n_types']}")
    if metadata.get("new_diffscore") is not None:
        print(f"  Do kho (new_diffScore): {metadata['new_diffscore']}  [{metadata['difficulty_tier']}]"
              f"   <- RANK levels with THIS (real-play validated)")
    if metadata["difficulty"] is not None:
        c = metadata["score_components"]
        print(f"  final_score (OLD chaos, visual complexity — NOT player-difficulty): {metadata['difficulty']}")
        print(f"    layout={c['layout']} inter={c['inter_group']} intra={c['intra_group']} "
              f"cover100={c['cover100']} pickdiv={c['pickable_diversity']}")
    print(f"  Type distribution: {metadata['type_distribution']}")

    if save:
        data["metadata"] = metadata
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        print(f"\nMetadata saved into {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_level.py <path-to-level.json> [--save]")
        sys.exit(1)
    save_flag = "--save" in sys.argv
    target = [a for a in sys.argv[1:] if not a.startswith("--")][0]
    analyze(target, save=save_flag)
