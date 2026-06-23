"""
Tile Level Metadata & Collection System
========================================
Manages metadata, pinned lists, and CLI interface.

Metadata schema designed for AI/MCP agent scanning:
- Each level/board/layer has structured metadata
- Hashtags for fast filtering
- JSON files with consistent naming

Created by Tran Ngoc Hai | Telegram @OrangeTran
"""

import json, os, time

# ─────────────────────────────────────────────────────────────
# Metadata System
# ─────────────────────────────────────────────────────────────

METADATA_VERSION = 1

def build_board_metadata(board, engine_params=None, solver_result=None, tags=None):
    """
    Build complete metadata for a board.

    Schema designed for AI/MCP agent consumption:
    - Flat structure for easy querying
    - Hashtags for fast grep/search
    - All IDs are strings for JSON compatibility
    """
    layers_meta = []
    for li, layer in enumerate(board.layers):
        cells = layer.cells
        tile_counts = {}
        xs = [c.x for c in cells]
        ys = [c.y for c in cells]
        for c in cells:
            if c.tile_id >= 0:
                tile_counts[c.tile_id] = tile_counts.get(c.tile_id, 0) + 1

        lm = {
            "layer_id": li,
            "cell_count": len(cells),
            "tile_types": len(tile_counts),
            "tile_distribution": tile_counts,
            "bounds": {
                "x_min": min(xs) if xs else 0,
                "x_max": max(xs) if xs else 0,
                "y_min": min(ys) if ys else 0,
                "y_max": max(ys) if ys else 0,
            },
            "has_half_grid": any(c.x % 1 != 0 or c.y % 1 != 0 for c in cells),
            "hashtags": [],
        }

        # Auto hashtags per layer
        if len(cells) > 30: lm["hashtags"].append("#large-layer")
        elif len(cells) < 10: lm["hashtags"].append("#small-layer")
        if lm["has_half_grid"]: lm["hashtags"].append("#staggered")
        if len(tile_counts) <= 2: lm["hashtags"].append("#easy-layer")
        elif len(tile_counts) >= 6: lm["hashtags"].append("#hard-layer")

        layers_meta.append(lm)

    # Board-level metadata
    all_cells = board.all_cells()
    total = len(all_cells)
    all_tile_counts = {}
    for c in all_cells:
        if c.tile_id >= 0:
            all_tile_counts[c.tile_id] = all_tile_counts.get(c.tile_id, 0) + 1

    meta = {
        "_meta_version": METADATA_VERSION,
        "_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "board_name": board.name,
        "total_cells": total,
        "total_layers": len(board.layers),
        "cells_divisible_by_3": total % 3 == 0,
        "tile_types_used": len(all_tile_counts),
        "tile_distribution": all_tile_counts,
        "all_x3": all(v % 3 == 0 for v in all_tile_counts.values()) if all_tile_counts else False,
        "layers": layers_meta,
        "hashtags": list(tags) if tags else [],
    }

    # Auto hashtags for board
    auto_tags = set(meta["hashtags"])
    nl = len(board.layers)
    if nl <= 3: auto_tags.add("#few-layers")
    elif nl <= 6: auto_tags.add("#medium-layers")
    elif nl <= 10: auto_tags.add("#many-layers")
    else: auto_tags.add("#deep-stack")

    if total < 50: auto_tags.add("#small-board")
    elif total < 100: auto_tags.add("#medium-board")
    elif total < 150: auto_tags.add("#large-board")
    else: auto_tags.add("#huge-board")

    if meta["cells_divisible_by_3"]: auto_tags.add("#valid-x3")
    else: auto_tags.add("#remainder-cells")

    # Engine params
    if engine_params:
        meta["generation"] = engine_params
        cc = engine_params.get("color_count", 0)
        if cc <= 3: auto_tags.add("#easy-colors")
        elif cc <= 5: auto_tags.add("#medium-colors")
        else: auto_tags.add("#hard-colors")
        if engine_params.get("hard_code", 0) >= 2: auto_tags.add("#hard-mode")

    # Solver results
    if solver_result:
        meta["solvability"] = {
            "solve_rate": solver_result.get("solve_rate"),
            "deadlock_rate": solver_result.get("deadlock_rate"),
            "min_moves": solver_result.get("min_moves"),
            "avg_moves": solver_result.get("avg_moves"),
            "complexity_score": solver_result.get("complexity_score"),
            "complexity_label": solver_result.get("complexity_label"),
        }
        sr = solver_result.get("solve_rate", 0)
        if sr >= 90: auto_tags.add("#very-solvable")
        elif sr >= 60: auto_tags.add("#solvable")
        elif sr >= 30: auto_tags.add("#challenging")
        else: auto_tags.add("#very-hard")

        cl = solver_result.get("complexity_label", "")
        if cl: auto_tags.add(f"#complexity-{cl.lower().replace(' ', '-')}")

        # New scoring system fields
        if solver_result.get("new_final_score") is not None:
            meta["difficulty_score"] = {
                "layout": solver_result.get("new_layout"),
                "inter_group": solver_result.get("new_inter_group"),
                "intra_group": solver_result.get("new_intra_group"),
                "cover100": solver_result.get("new_cover100"),
                "stripped_triples": solver_result.get("new_stripped"),
                "final_score": solver_result.get("new_final_score"),
                "weights": solver_result.get("new_weights"),
            }
            ns = solver_result.get("new_final_score", 0)
            if ns > 50: auto_tags.add("#high-difficulty")
            elif ns > 20: auto_tags.add("#medium-difficulty")
            else: auto_tags.add("#low-difficulty")
            if solver_result.get("new_cover100", 0) > 30:
                auto_tags.add("#many-covered")

    meta["hashtags"] = sorted(auto_tags)
    return meta


def export_with_metadata(board, out_dir, engine=None, solver_result=None,
                          tags=None, engine_params=None):
    """
    Export board with full metadata.
    Creates:
      {out_dir}/
        board_{name}.json          — tile data + metadata
        board_{name}.meta.json     — metadata only (for AI scanning)
    """
    os.makedirs(out_dir, exist_ok=True)

    # Build engine params dict
    if engine and not engine_params:
        engine_params = {
            "color_count": engine.color_count,
            "hard_code": engine.hard_code,
            "level_number": engine.level_number,
            "less_type": engine.less_type,
            "up_easy": engine.up_easy,
            "top2_easy": engine.top2_easy,
            "distance": engine.distance,
            "binding": engine.binding,
        }

    meta = build_board_metadata(board, engine_params, solver_result, tags)

    # Full export (data + meta)
    safe = board.name.replace(" ", "_").replace("#", "").replace("/", "_").replace(".", "_")
    data = {
        "metadata": meta,
        "layers": [{
            "id": l.id,
            "cells": [{"x": c.x, "y": c.y, "tile": c.tile_id} for c in l.cells]
        } for l in board.layers],
    }
    data_path = os.path.join(out_dir, f"board_{safe}.json")
    with open(data_path, "w") as f:
        json.dump(data, f, indent=2)

    # Meta-only file (lightweight, for AI scanning)
    meta_path = os.path.join(out_dir, f"board_{safe}.meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    return data_path, meta_path


def build_collection_index(out_dir):
    """
    Scan a directory and build an index of all .meta.json files.
    Creates _index.json for fast AI/MCP lookup.
    """
    index = {"_type": "tile_level_collection", "_version": METADATA_VERSION,
             "_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"), "boards": []}

    for fname in sorted(os.listdir(out_dir)):
        if not fname.endswith(".meta.json"):
            continue
        path = os.path.join(out_dir, fname)
        with open(path) as f:
            meta = json.load(f)
        index["boards"].append({
            "file": fname.replace(".meta.json", ".json"),
            "name": meta.get("board_name", ""),
            "cells": meta.get("total_cells", 0),
            "layers": meta.get("total_layers", 0),
            "hashtags": meta.get("hashtags", []),
            "solve_rate": (meta.get("solvability") or {}).get("solve_rate"),
            "complexity": (meta.get("solvability") or {}).get("complexity_label"),
        })

    index["total"] = len(index["boards"])
    idx_path = os.path.join(out_dir, "_index.json")
    with open(idx_path, "w") as f:
        json.dump(index, f, indent=2)
    return idx_path


# ─────────────────────────────────────────────────────────────
# Pinned List — save/load favorite levels
# ─────────────────────────────────────────────────────────────

PINNED_FILE = os.path.join(os.path.dirname(__file__), "pinned_levels.json")


def load_pinned():
    if os.path.exists(PINNED_FILE):
        try:
            with open(PINNED_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict) and "items" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            pass  # corrupted file, reset
    return {"items": []}


def save_pinned(data):
    with open(PINNED_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_pinned(file, board_idx, note="", tags=None, stats=None):
    """Add a level to pinned list."""
    data = load_pinned()
    # Check duplicate
    for item in data["items"]:
        if item["file"] == file and item["board"] == board_idx:
            # Update existing
            if note: item["note"] = note
            if tags: item["tags"] = list(set(item.get("tags", []) + list(tags)))
            if stats: item["stats"] = stats
            save_pinned(data)
            return item

    item = {
        "file": file,
        "board": board_idx,
        "note": note,
        "tags": list(tags) if tags else [],
        "stats": stats or {},
        "pinned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data["items"].append(item)
    save_pinned(data)
    return item


def remove_pinned(file, board_idx):
    data = load_pinned()
    data["items"] = [i for i in data["items"]
                     if not (i["file"] == file and i["board"] == board_idx)]
    save_pinned(data)


def get_pinned():
    return load_pinned().get("items", [])


# ─────────────────────────────────────────────────────────────
# Project System — isolated workspaces
# ─────────────────────────────────────────────────────────────

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
PROJECTS_INDEX = os.path.join(PROJECTS_DIR, "_projects.json")


def _ensure_projects_dir():
    os.makedirs(PROJECTS_DIR, exist_ok=True)


def _load_projects_index():
    _ensure_projects_dir()
    if os.path.exists(PROJECTS_INDEX):
        try:
            with open(PROJECTS_INDEX) as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            pass
    return {"active": None, "projects": []}


def _save_projects_index(data):
    _ensure_projects_dir()
    with open(PROJECTS_INDEX, "w") as f:
        json.dump(data, f, indent=2)


def create_project(name, description=""):
    """Create a new project with its own levels folder + pinned list."""
    _ensure_projects_dir()
    # Sanitize name for folder
    safe = name.replace(" ", "_").replace("/", "_").replace("\\", "_")
    proj_dir = os.path.join(PROJECTS_DIR, safe)
    os.makedirs(proj_dir, exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "levels"), exist_ok=True)
    os.makedirs(os.path.join(proj_dir, "exports"), exist_ok=True)

    # Project config
    config = {
        "name": name,
        "description": description,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "levels_dir": os.path.join(proj_dir, "levels"),
        "exports_dir": os.path.join(proj_dir, "exports"),
    }
    with open(os.path.join(proj_dir, "project.json"), "w") as f:
        json.dump(config, f, indent=2)

    # Empty pinned list for this project
    with open(os.path.join(proj_dir, "pinned.json"), "w") as f:
        json.dump({"items": []}, f, indent=2)

    # Register in index
    idx = _load_projects_index()
    # Don't duplicate
    if not any(p["folder"] == safe for p in idx["projects"]):
        idx["projects"].append({"name": name, "folder": safe, "created": config["created"]})
    idx["active"] = safe
    _save_projects_index(idx)

    return proj_dir


def list_projects():
    """List all projects."""
    idx = _load_projects_index()
    result = []
    for p in idx["projects"]:
        proj_dir = os.path.join(PROJECTS_DIR, p["folder"])
        cfg_path = os.path.join(proj_dir, "project.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
            # Count levels
            ldir = cfg.get("levels_dir", "")
            n_files = len([f for f in os.listdir(ldir) if f.endswith(".json")]) if os.path.isdir(ldir) else 0
            result.append({
                "name": cfg["name"],
                "folder": p["folder"],
                "description": cfg.get("description", ""),
                "created": cfg.get("created", ""),
                "levels_dir": ldir,
                "exports_dir": cfg.get("exports_dir", ""),
                "n_files": n_files,
                "active": p["folder"] == idx.get("active"),
            })
    return result


def get_active_project():
    """Get the currently active project config, or None."""
    idx = _load_projects_index()
    active = idx.get("active")
    if not active:
        return None
    proj_dir = os.path.join(PROJECTS_DIR, active)
    cfg_path = os.path.join(proj_dir, "project.json")
    if not os.path.exists(cfg_path):
        return None
    with open(cfg_path) as f:
        cfg = json.load(f)
    cfg["folder"] = active
    cfg["proj_dir"] = proj_dir
    cfg["pinned_file"] = os.path.join(proj_dir, "pinned.json")
    return cfg


def set_active_project(folder_name):
    """Switch active project."""
    idx = _load_projects_index()
    idx["active"] = folder_name
    _save_projects_index(idx)


def delete_project(folder_name):
    """Delete a project and all its data."""
    import shutil
    idx = _load_projects_index()
    idx["projects"] = [p for p in idx["projects"] if p["folder"] != folder_name]
    if idx["active"] == folder_name:
        idx["active"] = idx["projects"][0]["folder"] if idx["projects"] else None
    _save_projects_index(idx)
    proj_dir = os.path.join(PROJECTS_DIR, folder_name)
    if os.path.isdir(proj_dir):
        shutil.rmtree(proj_dir)


def import_files_to_project(folder_name, file_paths):
    """Copy JSON files into a project's levels folder."""
    import shutil
    proj_dir = os.path.join(PROJECTS_DIR, folder_name)
    levels_dir = os.path.join(proj_dir, "levels")
    os.makedirs(levels_dir, exist_ok=True)
    copied = 0
    for src in file_paths:
        if os.path.isfile(src) and src.endswith(".json"):
            dst = os.path.join(levels_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            copied += 1
    return copied


def import_folder_to_project(folder_name, src_dir):
    """Copy all JSON files from a folder into a project's levels folder."""
    files = [os.path.join(src_dir, f) for f in os.listdir(src_dir)
             if f.endswith(".json") and not f.startswith("_")]
    return import_files_to_project(folder_name, files)


# ─────────────────────────────────────────────────────────────
# CLI Interface — for automation and AI agents
# ─────────────────────────────────────────────────────────────

CLI_HELP = """
TILE LEVEL SIMULATOR — CLI REFERENCE
======================================

IMPORT:
  import tile_level_simulator as tls
  import tile_metadata as meta

BOARD OPERATIONS:
  tls.list_level_files()              → ['level0.json', 'level1.json', ...]
  tls.get_board_count('level1.json')  → 100
  board = tls.load_board('level1.json', 0)
  board.total_cells()                 → 126
  len(board.layers)                   → 8

ENGINE (generate tiles):
  engine = tls.TEEngine()
  engine.color_count = 4              # 2-9
  engine.hard_code = 2                # 0-3
  engine.level_number = 200
  engine.less_type = True             # Knob 1
  engine.up_easy = True               # Knob 2
  engine.top2_easy = True             # Knob 4
  engine.distance = 5                 # Knob 3 (level 101+)
  engine.val_replace = True           # Knob 5 (level 51+)
  engine.val_mode = 1                 # 0-3
  engine.binding = "random"           # or "preset"
  stats = engine.generate(board)
  → stats["dist"]                     # {0: 33, 1: 30, ...}
  → stats["eff_cc"]                   # effective color count
  → stats["solvable"]                 # True/False
  → stats["multiples_of_3"]           # True/False

SOLVER (analyze solvability):
  result = tls.TileSolver.analyze(board, max_steps=500)
  → result["solve_rate"]              # 65.0 (percent)
  → result["deadlock_rate"]           # 35.0
  → result["min_moves"]               # 126
  → result["avg_moves"]               # 130.5
  → result["complexity_score"]        # 49
  → result["complexity_label"]        # "Medium"
  → result["layer_analysis"]          # per-layer stats

METADATA:
  m = meta.build_board_metadata(board, engine_params, solver_result, tags)
  → m["hashtags"]                     # ['#solvable', '#medium-board', ...]
  → m["layers"][0]["cell_count"]      # 21
  → m["solvability"]["solve_rate"]    # 65.0

EXPORT WITH METADATA:
  meta.export_with_metadata(board, "./output", engine, solver_result,
                             tags={"#my-custom-tag"})
  → creates board_xxx.json + board_xxx.meta.json

COLLECTION INDEX:
  meta.build_collection_index("./output")
  → creates _index.json (scannable by AI/MCP)

PINNED LIST:
  meta.add_pinned("level1.json", 0, note="great layout", tags=["#favorite"])
  meta.get_pinned()                   → [{"file": ..., "board": ..., "note": ...}]
  meta.remove_pinned("level1.json", 0)

BATCH SEARCH:
  for cc in range(2, 10):
      engine.color_count = cc
      board.clear_tiles()
      engine.generate(board)
      r = tls.TileSolver.analyze(board, max_steps=200)
      print(f"cc={cc}: solve={r['solve_rate']}% [{r['complexity_label']}]")

BATCH EXPORT:
  for fname in tls.list_level_files()[:5]:
      for bi in range(3):
          b = tls.load_board(fname, bi)
          if not b: continue
          engine.generate(b)
          r = tls.TileSolver.analyze(b, max_steps=100)
          meta.export_with_metadata(b, "./batch_out", engine, r)
  meta.build_collection_index("./batch_out")
""".strip()


def cli_help():
    """Print full CLI reference."""
    print(CLI_HELP)


if __name__ == "__main__":
    cli_help()
