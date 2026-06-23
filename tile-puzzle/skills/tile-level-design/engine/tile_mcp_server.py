"""
Tile Level Simulator — MCP Server
==================================
Exposes tile simulation tools to Claude/AI agents via MCP protocol.

Usage:
  python tile_mcp_server.py              (stdio mode for Claude Code)

MCP Config for Claude Code settings.json:
  {
    "mcpServers": {
      "tile-sim": {
        "command": "python",
        "args": ["d:/_Rac/tile_explore/tile_mcp_server.py"]
      }
    }
  }

Created by Tran Ngoc Hai | Telegram @OrangeTran
"""

import sys, os

# Ensure project dir is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
import tile_api as api

mcp = FastMCP("tile-sim", instructions="""
Tile Level Simulator MCP Server — tools for tile-matching puzzle level design.

Key workflows:
1. Load board → generate tiles → score difficulty → export
2. Bulk score 1000+ levels → get difficulty curve data
3. Create/edit layouts → test with different params
4. Search levels by criteria → pin favorites

All board data is passed as JSON dicts (stateless).
""")


# ─────────────────────────────────────────────
# Board Management
# ─────────────────────────────────────────────

@mcp.tool()
def list_level_files(directory: str = None) -> list[str]:
    """List available level JSON files in the levels directory."""
    return api.api_list_files(directory)


@mcp.tool()
def load_board(file: str, board_idx: int = 0, directory: str = None) -> dict:
    """Load a board from a level file. Returns board dict with layers and cells."""
    return api.api_load_board(file, board_idx, directory)


@mcp.tool()
def load_board_from_path(filepath: str, board_idx: int = 0) -> dict:
    """Load a board from an absolute file path."""
    return api.api_load_board_from_path(filepath, board_idx)


@mcp.tool()
def get_board_count(file: str, directory: str = None) -> int:
    """Get the number of boards in a level file."""
    return api.api_get_board_count(file, directory)


@mcp.tool()
def create_board(name: str, layers_spec: list[dict]) -> dict:
    """
    Create a new board from scratch.

    Args:
        name: Board name
        layers_spec: List of layer dicts, each with "cells" key.
                     Example: [{"cells": [{"x":0,"y":0}, {"x":1,"y":0}]}]
    """
    return api.api_create_board(name, layers_spec)


@mcp.tool()
def edit_board(board_dict: dict, action: str, **kwargs) -> dict:
    """
    Edit a board. Actions:
    - "add_layer": add layer with cells=[{"x":0,"y":0},...] on top
    - "remove_layer": remove layer at layer_idx=N
    - "move_layer": move layer from from_idx=N to to_idx=M
    - "copy_layer": copy layer at source_idx=N, optional insert_idx=M
    - "add_cells": add cells to layer_idx=N, cells=[{"x":0,"y":0},...]
    - "remove_cells": remove cells from layer_idx=N, cells=[{"x":0,"y":0},...]
    """
    if action == "add_layer":
        return api.api_add_layer(board_dict, kwargs.get("cells", []))
    elif action == "remove_layer":
        return api.api_remove_layer(board_dict, kwargs.get("layer_idx", 0))
    elif action == "move_layer":
        return api.api_move_layer(board_dict, kwargs.get("from_idx", 0), kwargs.get("to_idx", 0))
    elif action == "copy_layer":
        return api.api_copy_layer(board_dict, kwargs.get("source_idx", 0), kwargs.get("insert_idx"))
    elif action == "add_cells":
        return api.api_add_cells(board_dict, kwargs.get("layer_idx", 0), kwargs.get("cells", []))
    elif action == "remove_cells":
        return api.api_remove_cells(board_dict, kwargs.get("layer_idx", 0), kwargs.get("cells", []))
    return {"error": f"Unknown action: {action}"}


@mcp.tool()
def get_board_info(board_dict: dict) -> dict:
    """Get board summary: cells, layers, bounds, tile distribution."""
    return api.api_get_board_info(board_dict)


# ─────────────────────────────────────────────
# Level Generation
# ─────────────────────────────────────────────

@mcp.tool()
def generate_tiles(board_dict: dict, params: dict = None) -> dict:
    """
    Generate tiles on a board and compute difficulty score.

    Args:
        board_dict: Board data (from load_board or create_board)
        params: Generation parameters. Keys:
            color_count (2-9), hard_code (0-3), level_number (1-2000),
            less_type, up_easy, top2_easy, top3_easy, top4_easy (bool),
            distance (0-15),
            val_replace (bool), val_mode (0-3), binding ("random"/"preset"),
            validate (bool), custom_triples (dict: {type_id: triple_count})

    Returns: {board, stats, score}
    """
    return api.api_generate(board_dict, params)


@mcp.tool()
def auto_generate(board_dict: dict, params: dict = None,
                  target: dict = None, max_attempts: int = 200,
                  samples_per_attempt: int = 15) -> dict:
    """
    Generate tiles repeatedly until score matches target criteria.
    Runs server-side in 1 call — no need for AI loop.

    Args:
        board_dict: Board data
        params: Generation params (color_count, knobs, etc.)
        target: Score criteria. Any combination of:
            score_min/score_max: final score range (single-pass)
            layout_min/layout_max, inter_min/inter_max,
            intra_min/intra_max, cover_min/cover_max,
            stripped_min/stripped_max
            final_min_max: [lo, hi] — batch Min/Max final_score range
            inter_min_max: [lo, hi] — batch Min/Max inter_group range
            intra_min_max: [lo, hi] — batch Min/Max intra_group range
        max_attempts: Max tries (default 200)
        samples_per_attempt: Samples for Min/Max targets (default 15)

    Returns: {board, stats, score, attempts, matched}

    Example: auto_generate(board, {"color_count":4}, {"final_min_max":[10, 50]})
    → finds arrangement where batch Min/Max falls within [10, 50]
    """
    return api.api_auto_generate(board_dict, params, target, max_attempts, samples_per_attempt)


@mcp.tool()
def list_presets() -> dict:
    """List available difficulty presets with their parameter values."""
    return api.api_list_presets()


@mcp.tool()
def apply_preset(preset_name: str) -> dict:
    """Get generation parameters for a named preset."""
    return api.api_apply_preset(preset_name)


# ─────────────────────────────────────────────
# Difficulty Analysis
# ─────────────────────────────────────────────

@mcp.tool()
def score_level(board_dict: dict, weights: dict = None,
                samples: int = 150) -> dict:
    """
    Compute difficulty score for a board (tiles must be assigned).
    Default: 150 random strip samples → returns Min/Max for inter, intra, cover, final.
    Set samples=1 for single deterministic score.

    Returns: {layout, inter_group, intra_group, cover100, stripped, final_score, weights,
              inter_min, inter_max, intra_min, intra_max, final_min, final_max, ...}
    """
    return api.api_score(board_dict, weights, samples)


@mcp.tool()
def batch_score(board_dict: dict, params: dict = None,
                weights: dict = None, n_runs: int = 50) -> dict:
    """
    Run generate N times on same layout. Returns min/max/avg of all score components.
    Use this to measure the difficulty range of a layout.
    """
    return api.api_batch_score(board_dict, params, weights, n_runs)


@mcp.tool()
def bulk_score_levels(file_list: list[str] = None, params: dict = None,
                      weights: dict = None, max_boards_per_file: int = 10,
                      samples: int = 150) -> list[dict]:
    """
    Score many levels at once with Min/Max (default 150 samples).
    Returns list of {file, board_idx, cells, layers, layout, inter_group, inter_min, inter_max, ..., final_score, final_min, final_max}.
    Set samples=1 for single-pass scoring (faster but no Min/Max).
    """
    return api.api_bulk_score(file_list, params, weights, max_boards_per_file, samples)


@mcp.tool()
def difficulty_curve(file_list: list[str] = None, params: dict = None,
                     weights: dict = None, max_boards_per_file: int = 100,
                     samples: int = 150) -> dict:
    """
    Score all boards across files with Min/Max, return data for plotting a difficulty curve.
    Returns: {levels: [{idx, file, board, final_score, final_min, final_max, ...}], summary: {count, min, max, avg}}
    """
    return api.api_difficulty_curve(file_list, params, weights, max_boards_per_file, samples)


@mcp.tool()
def bulk_score_folder(folder_path: str, weights: dict = None,
                      samples: int = 150) -> list[dict]:
    """
    Score ALL level files in a folder with Min/Max (default 150 samples).
    Works with any folder path — not limited to default levels directory.
    Boards must already have tiles assigned (stones format with "i" fields).

    Returns: list of {file, cells, layers, types, layout, inter_group, inter_min, inter_max, ..., final_score, final_min, final_max}
    Set samples=1 for single-pass scoring (faster but no Min/Max).
    """
    import os
    results = []
    files = sorted([f for f in os.listdir(folder_path) if f.endswith('.json')])
    for fname in files:
        path = os.path.join(folder_path, fname)
        bd = api.api_load_board_from_path(path)
        if 'error' in bd:
            continue
        info = api.api_get_board_info(bd)
        score = api.api_score(bd, weights, samples)
        results.append({
            "file": fname,
            "cells": info["total_cells"],
            "layers": info["total_layers"],
            "types": len(info["tile_distribution"]),
            **score,
        })

    api.logger.log_event("bulk_score_folder", folder=folder_path,
                         count=len(results), samples=samples)
    return results


@mcp.tool()
def visualize_board(board_dict: dict) -> str:
    """
    Return a text visualization of the board layout.
    Shows each layer as a grid with tile type IDs.
    Useful for AI to understand board structure without GUI.
    """
    board = api.board_from_dict(board_dict)
    lines = []
    lines.append(f"Board: {board.name}")
    lines.append(f"Total: {board.total_cells()} cells, {len(board.layers)} layers")
    lines.append("")

    for li, layer in enumerate(board.layers):
        cells = layer.cells
        if not cells:
            lines.append(f"Layer {li}: (empty)")
            continue

        xs = [c.x for c in cells]
        ys = [c.y for c in cells]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(ys), max(ys)

        # Build grid
        cell_map = {}
        for c in cells:
            cell_map[(round(c.x * 2) / 2, round(c.y * 2) / 2)] = c.tile_id

        lines.append(f"Layer {li} ({len(cells)} cells, y={y_min:.1f}..{y_max:.1f}):")

        # Render top-to-bottom
        y = y_max
        while y >= y_min - 0.01:
            row = f"  y={y:5.1f} |"
            x = x_min
            while x <= x_max + 0.01:
                key = (round(x * 2) / 2, round(y * 2) / 2)
                if key in cell_map:
                    tid = cell_map[key]
                    if tid >= 0:
                        row += f"{tid:3d}"
                    else:
                        row += "  ."
                else:
                    row += "   "
                x += 0.5
            lines.append(row)
            y -= 0.5
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def analyze_solvability(board_dict: dict, sims: int = 500) -> dict:
    """
    Run Monte Carlo solvability analysis.
    Returns: solve_rate, deadlock_rate, min/avg/max_moves, complexity_score, new scoring data.
    """
    return api.api_analyze(board_dict, sims)


@mcp.tool()
def full_report(board_dict: dict, sims: int = 500, samples: int = 150,
                weights: dict = None) -> dict:
    """
    Combined scoring + solvability in one call.
    Returns: {scoring: {layout, inter_min, inter_max, final_min, final_max, ...},
              solvability: {solve_rate, deadlock_rate, min/avg/max_moves, ...}}
    """
    return api.api_full_report(board_dict, sims, samples, weights)


@mcp.tool()
def play_level(board_dict: dict, params: dict = None) -> dict:
    """
    Open a playable triple-match window for the user to test the level.

    If the board has no tiles assigned, generates them first using params.
    The play window opens on the user's screen — they can pick tiles,
    use buffs (Shuffle, Undo, +1 Slot), and see if the level is winnable.

    Args:
        board_dict: Board data (from load_board or generate_tiles)
        params: Generation params (only used if tiles not yet assigned)

    Returns: confirmation that play window was opened
    """
    return api.api_play_level(board_dict, params)


# ─────────────────────────────────────────────
# Search & Order
# ─────────────────────────────────────────────

@mcp.tool()
def search_levels(criteria: dict, file_list: list[str] = None,
                  params: dict = None) -> list[dict]:
    """
    Find boards matching criteria.

    criteria keys: cells_min, cells_max, layers_min, layers_max, score_min, score_max
    Returns list of matching boards with scores.
    """
    return api.api_search(criteria, file_list, params)


# ─────────────────────────────────────────────
# Unity-Style Report
# ─────────────────────────────────────────────

@mcp.tool()
def export_unity_report(folder_path: str, output_csv: str = None,
                        samples: int = 100) -> dict:
    """
    Generate Unity-style difficulty report with Min/Max InterGroup and IntraGroup.
    Regenerates N times per level using the ORIGINAL color count from each file.

    Output CSV matches Unity BatchLevelDifficultyReport format.

    Example: export_unity_report("D:/TE_3_60", samples=100)
    """
    return api.api_export_unity_report(folder_path, output_csv, samples)


# ─────────────────────────────────────────────
# Mass Level Production Pipeline
# ─────────────────────────────────────────────

@mcp.tool()
def generate_random_board(name: str = "auto", num_layers: int = 4,
                          cells_per_layer: int = 15, shape: str = "diamond",
                          shrink_rate: float = 0.7, stagger: bool = True) -> dict:
    """
    Create a random board layout with specified shape.
    Shapes: "diamond" (most common), "rect", "hex", "random"
    shrink_rate: 0.5=steep pyramid, 1.0=same size all layers
    """
    return api.api_generate_random_board(name, num_layers, cells_per_layer,
                                          shape, shrink_rate, stagger)


@mcp.tool()
def generate_level_batch(count: int = 100, layout_config: dict = None,
                         gen_params: dict = None, target: dict = None,
                         max_attempts_per_level: int = 50,
                         output_folder: str = None) -> dict:
    """
    Create N quality levels in 1 call. The KEY tool for mass production.

    Args:
        count: Number of levels (10-1000+)
        layout_config: Randomization ranges:
            num_layers: [min, max], cells_per_layer: [min, max],
            shapes: ["diamond","hex"], shrink_rate: [min, max]
        gen_params: {color_count, validate, knobs...}
        target: Score criteria {score_min, score_max}
        output_folder: Export path (creates folder if needed)

    Example: generate_level_batch(100, {"num_layers":[3,6]},
             {"color_count":4}, {"score_min":20,"score_max":80},
             output_folder="D:/levels/batch1")
    """
    return api.api_generate_level_batch(count, layout_config, gen_params,
                                         target, max_attempts_per_level, output_folder)


@mcp.tool()
def generate_difficulty_progression(total_levels: int = 200,
                                     difficulty_curve: str = "linear",
                                     score_start: float = 10, score_end: float = 120,
                                     layout_config: dict = None,
                                     gen_params: dict = None,
                                     output_folder: str = None,
                                     max_attempts_per_level: int = 100) -> dict:
    """
    Create levels following a difficulty curve from easy to hard.

    Curves: "linear", "ease_in" (slow start), "ease_out" (fast start), "s_curve" (smooth)
    Automatically scales layout complexity with difficulty.

    Example: generate_difficulty_progression(200, "s_curve", 10, 120,
             gen_params={"color_count":4}, output_folder="D:/levels/progression")
    """
    return api.api_generate_difficulty_progression(
        total_levels, difficulty_curve, score_start, score_end,
        layout_config, gen_params, output_folder, max_attempts_per_level)


@mcp.tool()
def clone_and_vary(board_dict: dict, count: int = 10,
                   vary_params: bool = True, vary_layout: bool = True,
                   gen_params: dict = None, target: dict = None,
                   output_folder: str = None) -> dict:
    """
    Create variants of a board by slightly modifying layout and/or params.
    Great for creating level families from a good base layout.
    """
    return api.api_clone_and_vary(board_dict, count, vary_params, vary_layout,
                                   gen_params, target, output_folder)


@mcp.tool()
def validate_level_set(folder_path: str, gen_params: dict = None,
                       checks: dict = None) -> dict:
    """
    Validate quality of all levels in a folder.

    checks: {min_cells, max_cells, min_layers, max_layers,
             score_range: [min,max], triples_balanced: true}

    Example: validate_level_set("D:/levels/batch1",
             checks={"min_cells":30, "score_range":[10,150], "triples_balanced":true})
    """
    return api.api_validate_level_set(folder_path, gen_params, checks)


@mcp.tool()
def export_level_set(source_folder: str, output_folder: str,
                     format: str = "stones", include_csv: bool = True,
                     rename_pattern: str = "Level_{idx:03d}") -> dict:
    """
    Export all levels from source to output folder with renaming.
    Optionally generates CSV index report.
    """
    return api.api_export_level_set(source_folder, output_folder, format,
                                     include_csv, rename_pattern)


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────

@mcp.tool()
def export_stones(board_dict: dict, path: str) -> dict:
    """Export board in stones/stacks format (for game engine)."""
    return api.api_export_stones(board_dict, path)


@mcp.tool()
def export_with_metadata(board_dict: dict, out_dir: str) -> dict:
    """Export board with full metadata (board.json + board.meta.json + _index.json)."""
    return api.api_export_metadata(board_dict, out_dir)


# ─────────────────────────────────────────────
# Pin & Project
# ─────────────────────────────────────────────

@mcp.tool()
def list_pinned() -> list[dict]:
    """Get all pinned (favorite) levels."""
    return api.api_list_pinned()


@mcp.tool()
def pin_level(file: str, board_idx: int, note: str = "") -> dict:
    """Pin a level to favorites."""
    return api.api_pin(file, board_idx, note)


@mcp.tool()
def unpin_level(file: str, board_idx: int) -> dict:
    """Remove a level from favorites."""
    return api.api_unpin(file, board_idx)


@mcp.tool()
def list_projects() -> list[dict]:
    """List all project workspaces."""
    return api.api_list_projects()


@mcp.tool()
def create_project(name: str, description: str = "") -> dict:
    """Create a new project workspace."""
    return api.api_create_project(name, description)


@mcp.tool()
def switch_project(name: str) -> dict:
    """Switch to a different project workspace."""
    return api.api_switch_project(name)


# ─────────────────────────────────────────────
# Config & Logging
# ─────────────────────────────────────────────

@mcp.tool()
def get_weights() -> dict:
    """Get current scoring weights {X, Y, Z, K}."""
    return api.api_get_weights()


@mcp.tool()
def set_weights(X: float = None, Y: float = None,
                Z: float = None, K: float = None) -> dict:
    """Set scoring weights. Only specify the ones you want to change."""
    kwargs = {}
    if X is not None: kwargs["X"] = X
    if Y is not None: kwargs["Y"] = Y
    if Z is not None: kwargs["Z"] = Z
    if K is not None: kwargs["K"] = K
    return api.api_set_weights(**kwargs)


@mcp.tool()
def get_recent_logs(n: int = 50) -> list[dict]:
    """Get recent event log entries (for debugging). Each entry has ts, event, and details."""
    return api.api_get_logs(n)


# ─────────────────────────────────────────────
# MCP Resources
# ─────────────────────────────────────────────

@mcp.resource("tile://weights")
def resource_weights() -> str:
    """Current scoring weights."""
    import json
    return json.dumps(api.api_get_weights())


@mcp.resource("tile://pinned")
def resource_pinned() -> str:
    """Current pinned levels list."""
    import json
    return json.dumps(api.api_list_pinned())


@mcp.resource("tile://projects")
def resource_projects() -> str:
    """Available projects."""
    import json
    return json.dumps(api.api_list_projects())


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
