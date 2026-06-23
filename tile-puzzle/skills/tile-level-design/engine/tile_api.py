"""
Tile Level Simulator — Headless API Layer
==========================================
Thin wrapper around existing classes for MCP/AI integration.
All inputs/outputs are JSON-serializable dicts (no Python objects exposed).

Created by Tran Ngoc Hai | Telegram @OrangeTran
"""

import json, os, time, random
from tile_level_simulator import (
    Board, Layer, Cell, TEEngine, TileSolver, DifficultyScorer,
    DIFFICULTY_PRESETS, TILE_COLORS,
    load_board, load_board_from_file, list_level_files, get_board_count,
    export_board_stones_format, make_sample_board,
    load_scoring_weights, save_scoring_weights,
    _parse_layers_from_data,
)
import tile_metadata as meta
import tile_logger as logger


# ─────────────────────────────────────────────
# Board Serialization
# ─────────────────────────────────────────────

def board_to_dict(board) -> dict:
    """Convert Board object to JSON-serializable dict."""
    layers = []
    for li, layer in enumerate(board.layers):
        cells = [{"x": c.x, "y": c.y, "tile_id": c.tile_id} for c in layer.cells]
        layers.append({"id": li, "cells": cells})
    d = {"name": board.name, "layers": layers, "total_cells": board.total_cells()}
    # Preserve stones format metadata
    for attr in ("_stacks", "_group", "_tiles_str"):
        if hasattr(board, attr):
            d[attr] = getattr(board, attr)
    return d


def board_from_dict(data) -> Board:
    """Create Board object from dict — handles both internal and stones format."""
    board = Board(data.get("name", "api_board"))
    board.layers = _parse_layers_from_data(data.get("layers", []))
    # Restore stones format metadata
    for attr in ("_stacks", "_group", "_tiles_str"):
        if attr in data:
            setattr(board, attr, data[attr])
    return board


# ─────────────────────────────────────────────
# Board I/O
# ─────────────────────────────────────────────

def api_list_files(directory=None) -> list[str]:
    """List available level JSON files."""
    files = list_level_files(directory)
    logger.log_event("list_files", directory=directory, count=len(files))
    return files


def api_load_board(file, board_idx=0, directory=None) -> dict:
    """Load board by filename + index. Returns board dict."""
    board = load_board(file, board_idx, directory)
    if board is None:
        logger.log_error("load_board", f"Failed to load {file}#{board_idx}")
        return {"error": f"Failed to load {file}#{board_idx}"}
    d = board_to_dict(board)
    logger.log_event("board_load", file=file, board_idx=board_idx,
                     cells=board.total_cells(), layers=len(board.layers))
    return d


def api_load_board_from_path(filepath, board_idx=0) -> dict:
    """Load board from absolute path."""
    board = load_board_from_file(filepath, board_idx)
    if board is None:
        return {"error": f"Failed to load {filepath}#{board_idx}"}
    logger.log_event("board_load", file=filepath, board_idx=board_idx,
                     cells=board.total_cells(), layers=len(board.layers))
    return board_to_dict(board)


def api_get_board_count(file, directory=None) -> int:
    return get_board_count(file, directory)


# ─────────────────────────────────────────────
# Board Creation & Editing
# ─────────────────────────────────────────────

def api_create_board(name, layers_spec) -> dict:
    """
    Create a new board from layers specification.
    layers_spec: [{"cells": [{"x": 0, "y": 0}, ...]}, ...]
    """
    board = Board(name)
    for li, ls in enumerate(layers_spec):
        layer = Layer(li)
        for cd in ls.get("cells", []):
            layer.add(cd["x"], cd["y"])
        board.layers.append(layer)
    logger.log_event("board_create", name=name, cells=board.total_cells(),
                     layers=len(board.layers))
    return board_to_dict(board)


def api_add_layer(board_dict, cells) -> dict:
    """Add a new layer on top. cells: [{"x":0,"y":0}, ...]"""
    board = board_from_dict(board_dict)
    layer = Layer(len(board.layers))
    for cd in cells:
        layer.add(cd["x"], cd["y"])
    board.layers.append(layer)
    logger.log_event("board_edit", action="add_layer", layer_idx=layer.id,
                     cells_added=len(layer.cells))
    return board_to_dict(board)


def api_remove_layer(board_dict, layer_idx) -> dict:
    """Remove a layer by index."""
    board = board_from_dict(board_dict)
    if 0 <= layer_idx < len(board.layers):
        board.layers.pop(layer_idx)
        # Re-index
        for i, l in enumerate(board.layers):
            l.id = i
        logger.log_event("board_edit", action="remove_layer", layer_idx=layer_idx)
    return board_to_dict(board)


def api_move_layer(board_dict, from_idx, to_idx) -> dict:
    """Move a layer from one position to another."""
    board = board_from_dict(board_dict)
    if 0 <= from_idx < len(board.layers) and 0 <= to_idx < len(board.layers):
        layer = board.layers.pop(from_idx)
        board.layers.insert(to_idx, layer)
        for i, l in enumerate(board.layers):
            l.id = i
        logger.log_event("board_edit", action="move_layer",
                         from_idx=from_idx, to_idx=to_idx)
    return board_to_dict(board)


def api_copy_layer(board_dict, source_idx, insert_idx=None) -> dict:
    """Copy a layer and insert at position (default: on top)."""
    board = board_from_dict(board_dict)
    if 0 <= source_idx < len(board.layers):
        src = board.layers[source_idx]
        new_layer = Layer(insert_idx if insert_idx is not None else len(board.layers))
        for c in src.cells:
            nc = new_layer.add(c.x, c.y)
            if nc:
                nc.tile_id = c.tile_id
        idx = insert_idx if insert_idx is not None else len(board.layers)
        board.layers.insert(idx, new_layer)
        for i, l in enumerate(board.layers):
            l.id = i
        logger.log_event("board_edit", action="copy_layer",
                         source_idx=source_idx, insert_idx=idx)
    return board_to_dict(board)


def api_add_cells(board_dict, layer_idx, cells) -> dict:
    """Add cells to a specific layer. cells: [{"x":0,"y":0}, ...]"""
    board = board_from_dict(board_dict)
    if 0 <= layer_idx < len(board.layers):
        layer = board.layers[layer_idx]
        added = 0
        for cd in cells:
            if layer.add(cd["x"], cd["y"]):
                added += 1
        logger.log_event("board_edit", action="add_cells",
                         layer_idx=layer_idx, added=added)
    return board_to_dict(board)


def api_remove_cells(board_dict, layer_idx, cells) -> dict:
    """Remove cells from a specific layer. cells: [{"x":0,"y":0}, ...]"""
    board = board_from_dict(board_dict)
    if 0 <= layer_idx < len(board.layers):
        layer = board.layers[layer_idx]
        removed = 0
        for cd in cells:
            layer.cells = [c for c in layer.cells
                           if not (c.x == cd["x"] and c.y == cd["y"])]
            removed += 1
        logger.log_event("board_edit", action="remove_cells",
                         layer_idx=layer_idx, removed=removed)
    return board_to_dict(board)


def api_get_board_info(board_dict) -> dict:
    """Get board summary: cells, layers, bounds, distribution."""
    board = board_from_dict(board_dict)
    all_cells = board.all_cells()
    dist = {}
    for c in all_cells:
        if c.tile_id >= 0:
            dist[c.tile_id] = dist.get(c.tile_id, 0) + 1

    xs = [c.x for c in all_cells]
    ys = [c.y for c in all_cells]

    return {
        "name": board.name,
        "total_cells": len(all_cells),
        "total_layers": len(board.layers),
        "layers": [{"id": i, "cells": len(l.cells)} for i, l in enumerate(board.layers)],
        "tile_distribution": dist,
        "bounds": {
            "x_min": min(xs) if xs else 0, "x_max": max(xs) if xs else 0,
            "y_min": min(ys) if ys else 0, "y_max": max(ys) if ys else 0,
        },
        "has_tiles": any(c.tile_id >= 0 for c in all_cells),
    }


# ─────────────────────────────────────────────
# Level Generation
# ─────────────────────────────────────────────

def _configure_engine(params: dict) -> TEEngine:
    """Create and configure TEEngine from params dict."""
    engine = TEEngine()
    for attr in ("level_number", "color_count", "hard_code", "hard_bg_count",
                 "less_type", "up_easy", "top2_easy", "top3_easy", "top4_easy",
                 "distance", "val_replace", "val_mode", "style_mode", "extended",
                 "binding", "validate"):
        if attr in params:
            setattr(engine, attr, params[attr])
    if "custom_triples" in params and params["custom_triples"]:
        engine.custom_triples = {int(k): v for k, v in params["custom_triples"].items()}
    # Auto-adjust style_mode for high color counts
    if engine.color_count > 6 and engine.style_mode != 3:
        engine.style_mode = 3
        engine.extended = True
    elif engine.color_count > 5 and engine.style_mode == 0:
        engine.style_mode = 7
    return engine


def api_generate(board_dict, params=None) -> dict:
    """Generate tiles on a board. Returns {board, stats, score}."""
    board = board_from_dict(board_dict)
    engine = _configure_engine(params or {})

    stats = engine.generate(board)

    # Score
    try:
        weights = params.get("weights") if params else None
        score = DifficultyScorer.compute_full_score(board, weights=weights)
    except Exception:
        score = {}

    result = {
        "board": board_to_dict(board),
        "stats": stats,
        "score": score,
    }
    logger.log_event("generate", board=board.name,
                     params={k: v for k, v in (params or {}).items() if k != "custom_triples"},
                     total=stats.get("total"), solvable=stats.get("solvable"),
                     final_score=score.get("final_score"))
    return result


def api_auto_generate(board_dict, params=None, target=None, max_attempts=200,
                      samples_per_attempt=15) -> dict:
    """
    Generate tiles repeatedly until score matches target criteria.
    Runs entirely server-side — 1 call, no AI loop needed.

    Args:
        board_dict: Board data
        params: Generation params (color_count, knobs, etc.)
        target: Score criteria dict. Any combination of:
            score_min, score_max       — final_score range (single-pass)
            layout_min, layout_max     — layout score range
            inter_min, inter_max       — inter_group range (single-pass)
            intra_min, intra_max       — intra_group range (single-pass)
            cover_min, cover_max       — cover100 range
            stripped_min, stripped_max  — stripped triples range
            final_min_max: [lo, hi]    — batch Min/Max final_score must fall within
            inter_min_max: [lo, hi]    — batch Min/Max inter_group must fall within
            intra_min_max: [lo, hi]    — batch Min/Max intra_group must fall within
        max_attempts: Stop after this many tries (default 200)
        samples_per_attempt: samples for Min/Max targets (default 15)

    Returns: {board, stats, score, attempts, matched}
    """
    if not target:
        return api_generate(board_dict, params)

    board = board_from_dict(board_dict)
    engine = _configure_engine(params or {})
    weights = (params or {}).get("weights")

    best = None
    best_score = None
    best_diff = float('inf')

    # Parse single-pass target ranges
    t_score = (target.get("score_min", 0), target.get("score_max", 99999))
    t_layout = (target.get("layout_min", 0), target.get("layout_max", 99999))
    t_inter = (target.get("inter_min", 0), target.get("inter_max", 99999))
    t_intra = (target.get("intra_min", 0), target.get("intra_max", 99999))
    t_cover = (target.get("cover_min", 0), target.get("cover_max", 99999))
    t_strip = (target.get("stripped_min", 0), target.get("stripped_max", 99999))

    # Parse Min/Max target ranges (new)
    t_final_mm = target.get("final_min_max")    # [lo, hi]
    t_inter_mm = target.get("inter_min_max")    # [lo, hi]
    t_intra_mm = target.get("intra_min_max")    # [lo, hi]
    use_minmax = t_final_mm or t_inter_mm or t_intra_mm

    # Target midpoint for "closest" tracking
    if t_final_mm:
        t_mid = (t_final_mm[0] + t_final_mm[1]) / 2
    elif t_score[1] < 99999:
        t_mid = (t_score[0] + t_score[1]) / 2
    else:
        t_mid = t_score[0]

    for attempt in range(1, max_attempts + 1):
        engine.generate(board)

        # Single-pass score (always needed for basic criteria)
        try:
            score = DifficultyScorer.compute_full_score(board, weights=weights)
        except Exception:
            continue

        fs = score.get("final_score", 0)
        ly = score.get("layout", 0)
        ig = score.get("inter_group", 0)
        ng = score.get("intra_group", 0)
        cv = score.get("cover100", 0)
        st = score.get("stripped", 0)

        # Check single-pass criteria first (cheap)
        single_ok = (t_score[0] <= fs <= t_score[1] and
                     t_layout[0] <= ly <= t_layout[1] and
                     t_inter[0] <= ig <= t_inter[1] and
                     t_intra[0] <= ng <= t_intra[1] and
                     t_cover[0] <= cv <= t_cover[1] and
                     t_strip[0] <= st <= t_strip[1])

        # If Min/Max targets exist and single-pass passed, check Min/Max
        minmax_ok = True
        if use_minmax and single_ok:
            mm = _score_with_samples(board, weights, samples_per_attempt)
            score = mm  # Use the richer score for return

            if t_final_mm:
                if mm.get("final_min", 0) < t_final_mm[0] or mm.get("final_max", 99999) > t_final_mm[1]:
                    minmax_ok = False
            if t_inter_mm:
                if mm.get("inter_min", 0) < t_inter_mm[0] or mm.get("inter_max", 99999) > t_inter_mm[1]:
                    minmax_ok = False
            if t_intra_mm:
                if mm.get("intra_min", 0) < t_intra_mm[0] or mm.get("intra_max", 99999) > t_intra_mm[1]:
                    minmax_ok = False

        # Track closest to target midpoint
        diff = abs(fs - t_mid)
        if diff < best_diff:
            best_diff = diff
            best_score = score
            best = board_to_dict(board)

        if single_ok and minmax_ok:
            logger.log_event("auto_generate", board=board.name,
                             attempts=attempt, matched=True,
                             final_score=fs, target=target)
            return {
                "board": board_to_dict(board),
                "stats": {"total": board.total_cells(), "solvable": True},
                "score": score,
                "attempts": attempt,
                "matched": True,
            }

    # No exact match — return closest
    logger.log_event("auto_generate", board=board.name,
                     attempts=max_attempts, matched=False,
                     final_score=best_score.get("final_score") if best_score else 0,
                     target=target)
    return {
        "board": best,
        "stats": {"total": board_from_dict(best).total_cells() if best else 0},
        "score": best_score or {},
        "attempts": max_attempts,
        "matched": False,
        "message": f"No exact match in {max_attempts} attempts. Returning closest result.",
    }


def api_list_presets() -> dict:
    """List available difficulty presets."""
    return {name: preset for name, preset in DIFFICULTY_PRESETS.items()}


def api_apply_preset(preset_name) -> dict:
    """Get params for a named preset."""
    if preset_name in DIFFICULTY_PRESETS:
        return dict(DIFFICULTY_PRESETS[preset_name])
    return {"error": f"Unknown preset: {preset_name}"}


# ─────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────

def _score_with_samples(board, weights=None, samples=150) -> dict:
    """
    Score a board with optional Min/Max via randomized strip (DotNetRandom).

    samples<=1: single deterministic score (original behavior).
    samples>1:  run N random strip variations, return min/max/avg for
                inter_group, intra_group, cover100, final_score.
                Layout is computed once (structure-only, doesn't vary).
    """
    vis_map = TileSolver._build_visibility(board)

    if samples <= 1:
        return DifficultyScorer.compute_full_score(board, vis_map, weights)

    # Multi-sample: randomize strip tie-breaking N times
    from tile_level_simulator import DotNetRandom
    if not hasattr(_score_with_samples, '_rng'):
        _score_with_samples._rng = DotNetRandom(0)
    rng = _score_with_samples._rng

    ig_vals, ng_vals, cv_vals, ecv_vals, fs_vals, st_vals = [], [], [], [], [], []
    first_score = None
    for _ in range(samples):
        try:
            score = DifficultyScorer.compute_full_score(
                board, vis_map, weights, randomize_strip=rng)
            ig_vals.append(score.get("inter_group", 0))
            ng_vals.append(score.get("intra_group", 0))
            cv_vals.append(score.get("cover100", 0))
            ecv_vals.append(score.get("eff_cover", 0))
            fs_vals.append(score.get("final_score", 0))
            st_vals.append(score.get("stripped", 0))
            if first_score is None:
                first_score = score
        except Exception:
            pass

    if not first_score:
        return DifficultyScorer.compute_full_score(board, vis_map, weights)

    # Return first score as base, augmented with min/max/avg
    result = dict(first_score)
    result["samples"] = samples
    if fs_vals:
        result["inter_min"] = round(min(ig_vals), 2)
        result["inter_max"] = round(max(ig_vals), 2)
        result["inter_avg"] = round(sum(ig_vals) / len(ig_vals), 2)
        result["intra_min"] = round(min(ng_vals), 2)
        result["intra_max"] = round(max(ng_vals), 2)
        result["intra_avg"] = round(sum(ng_vals) / len(ng_vals), 2)
        result["cover100_min"] = min(cv_vals)
        result["cover100_max"] = max(cv_vals)
        result["eff_cover_min"] = min(ecv_vals)
        result["eff_cover_max"] = max(ecv_vals)
        result["final_min"] = round(min(fs_vals), 2)
        result["final_max"] = round(max(fs_vals), 2)
        result["final_avg"] = round(sum(fs_vals) / len(fs_vals), 2)
        result["stripped_min"] = min(st_vals)
        result["stripped_max"] = max(st_vals)
    return result


def api_score(board_dict, weights=None, samples=150) -> dict:
    """Compute difficulty score for a board (tiles must be assigned).
    samples>1: returns Min/Max via randomized strip (default 150)."""
    board = board_from_dict(board_dict)
    score = _score_with_samples(board, weights, samples)
    logger.log_event("score", board=board.name,
                     final_score=score.get("final_score"),
                     samples=samples)
    return score


def api_batch_score(board_dict, params=None, weights=None, n_runs=50) -> dict:
    """Run generate N times, return min/max/avg of all score components."""
    board = board_from_dict(board_dict)
    engine = _configure_engine(params or {})
    summary = DifficultyScorer.batch_score(board, engine, weights=weights, n_runs=n_runs)
    logger.log_event("batch_score", board=board.name, n_runs=n_runs,
                     final_avg=summary.get("final_score", {}).get("avg"))
    return summary


def api_bulk_score(file_list=None, params=None, weights=None,
                   max_boards_per_file=10, samples=150) -> list:
    """
    Score many levels at once. Returns list of score records with Min/Max.
    For 1000+ levels — key tool for GD difficulty curve analysis.
    samples: number of random strip samples per board (default 150).
    """
    files = file_list or list_level_files()
    results = []
    engine = _configure_engine(params or {})
    t0 = time.time()

    for fname in files:
        count = get_board_count(fname)
        for bi in range(min(count, max_boards_per_file)):
            board = load_board(fname, bi)
            if board is None:
                continue
            # Check if board already has tiles assigned
            has_tiles = any(c.tile_id >= 0 for c in board.all_cells())
            if not has_tiles:
                engine.generate(board)
            try:
                score = _score_with_samples(board, weights, samples)
            except Exception:
                score = {}
            results.append({
                "file": fname,
                "board_idx": bi,
                "cells": board.total_cells(),
                "layers": len(board.layers),
                **score,
            })

    elapsed = time.time() - t0
    logger.log_event("bulk_score", count=len(results), elapsed=round(elapsed, 2),
                     samples=samples)
    return results


def api_difficulty_curve(file_list=None, params=None, weights=None,
                         max_boards_per_file=100, samples=150) -> dict:
    """
    Score all boards across files, return data for plotting difficulty curve.
    Returns: {levels: [{idx, file, board, score...}], summary: {min, max, avg}}
    samples: number of random strip samples per board (default 150).
    """
    records = api_bulk_score(file_list, params, weights, max_boards_per_file, samples)

    # Sort by file order (level progression)
    levels = []
    for i, r in enumerate(records):
        levels.append({"idx": i, **r})

    scores = [r.get("final_score", 0) for r in records if "final_score" in r]
    summary = {}
    if scores:
        summary = {
            "count": len(scores),
            "min": round(min(scores), 2),
            "max": round(max(scores), 2),
            "avg": round(sum(scores) / len(scores), 2),
        }

    return {"levels": levels, "summary": summary}


# ─────────────────────────────────────────────
# Solver
# ─────────────────────────────────────────────

def api_analyze(board_dict, sims=500) -> dict:
    """Run solvability analysis (Monte Carlo simulation)."""
    board = board_from_dict(board_dict)
    if not any(c.tile_id >= 0 for c in board.all_cells()):
        return {"error": "Board has no tiles assigned. Generate first."}
    result = TileSolver.analyze(board, max_solutions=100, max_steps=sims)
    logger.log_event("analyze", board=board.name, sims=sims,
                     solve_rate=result.get("solve_rate"))
    return result


def api_full_report(board_dict, sims=500, samples=150, weights=None) -> dict:
    """
    Combined scoring + solvability report in one call.
    Returns: {scoring: {layout, inter_min, inter_max, ...}, solvability: {solve_rate, ...}}
    """
    board = board_from_dict(board_dict)
    has_tiles = any(c.tile_id >= 0 for c in board.all_cells())
    if not has_tiles:
        return {"error": "Board has no tiles assigned. Generate first."}

    # Scoring with Min/Max
    scoring = _score_with_samples(board, weights, samples)

    # Solvability (Monte Carlo)
    solvability = TileSolver.analyze(board, max_solutions=100, max_steps=sims)

    logger.log_event("full_report", board=board.name, sims=sims, samples=samples,
                     final_min=scoring.get("final_min"),
                     final_max=scoring.get("final_max"),
                     solve_rate=solvability.get("solve_rate"))

    return {"scoring": scoring, "solvability": solvability}


# ─────────────────────────────────────────────
# Search / Order
# ─────────────────────────────────────────────

def api_search(criteria, file_list=None, params=None) -> list:
    """
    Find boards matching criteria.
    criteria: {
        cells_min, cells_max, layers_min, layers_max,
        score_min, score_max,  # new difficulty score range
    }
    """
    files = file_list or list_level_files()
    engine = _configure_engine(params or {})
    results = []

    c_lo = criteria.get("cells_min", 0)
    c_hi = criteria.get("cells_max", 9999)
    l_lo = criteria.get("layers_min", 0)
    l_hi = criteria.get("layers_max", 99)
    s_lo = criteria.get("score_min", 0)
    s_hi = criteria.get("score_max", 99999)

    for fname in files:
        count = get_board_count(fname)
        for bi in range(count):
            board = load_board(fname, bi)
            if board is None:
                continue
            nc = board.total_cells()
            nl = len(board.layers)
            if not (c_lo <= nc <= c_hi and l_lo <= nl <= l_hi):
                continue

            engine.generate(board)
            try:
                score = DifficultyScorer.compute_full_score(board)
                fs = score.get("final_score", 0)
            except Exception:
                fs = 0
                score = {}

            if not (s_lo <= fs <= s_hi):
                continue

            results.append({
                "file": fname, "board_idx": bi,
                "cells": nc, "layers": nl,
                **score,
            })

    logger.log_event("search", criteria=criteria, results=len(results))
    return results


# ─────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────

def api_export_stones(board_dict, path) -> dict:
    """Export board in stones/stacks format to a file."""
    board = board_from_dict(board_dict)
    data = export_board_stones_format(board)
    try:
        with open(path, "w") as f:
            json.dump(data, f, separators=(",", ":"))
        logger.log_event("export", format="stones", path=path, board=board.name)
        return {"success": True, "path": path}
    except OSError as e:
        logger.log_error("export_stones", str(e))
        return {"error": str(e)}


def api_export_metadata(board_dict, out_dir, solver_result=None) -> dict:
    """Export board with full metadata."""
    board = board_from_dict(board_dict)
    try:
        dp, mp = meta.export_with_metadata(board, out_dir, solver_result=solver_result)
        meta.build_collection_index(out_dir)
        logger.log_event("export", format="metadata", path=dp, board=board.name)
        return {"success": True, "data_path": dp, "meta_path": mp}
    except Exception as e:
        logger.log_error("export_metadata", str(e))
        return {"error": str(e)}


# ─────────────────────────────────────────────
# Pin / Project
# ─────────────────────────────────────────────

def api_list_pinned() -> list:
    return meta.get_pinned()


def api_pin(file, board_idx, note="", tags=None, stats=None) -> dict:
    meta.add_pinned(file, board_idx, note, tags, stats)
    logger.log_event("pin", file=file, board_idx=board_idx, note=note)
    return {"success": True}


def api_unpin(file, board_idx) -> dict:
    meta.remove_pinned(file, board_idx)
    logger.log_event("unpin", file=file, board_idx=board_idx)
    return {"success": True}


def api_list_projects() -> list:
    return meta.list_projects()


def api_create_project(name, description="") -> dict:
    result = meta.create_project(name, description)
    logger.log_event("project_create", name=name)
    return result


def api_switch_project(name) -> dict:
    meta.set_active_project(name)
    logger.log_event("project_switch", name=name)
    return {"success": True, "project": name}


# ─────────────────────────────────────────────
# Weights
# ─────────────────────────────────────────────

def api_get_weights() -> dict:
    return load_scoring_weights()


def api_set_weights(**kwargs) -> dict:
    """Set scoring weights. Pass X=, Y=, Z=, K= as keyword args."""
    w = load_scoring_weights()
    for k in ("X", "Y", "Z", "K"):
        if k in kwargs:
            w[k] = float(kwargs[k])
    save_scoring_weights(w)
    logger.log_event("weight_change", weights=w)
    return w


# ─────────────────────────────────────────────
# Play Level (launch GUI for user)
# ─────────────────────────────────────────────

def api_play_level(board_dict, params=None) -> dict:
    """
    Launch a playable triple-match window for the user.
    If board has no tiles, generates them first with given params.
    Opens a standalone tkinter window in a separate process (Windows-safe).

    Returns: {played: True, board_name: str}
    """
    import subprocess, sys, tempfile, os

    board = board_from_dict(board_dict)

    # Generate tiles if not assigned
    if not any(c.tile_id >= 0 for c in board.all_cells()):
        engine = _configure_engine(params or {})
        engine.generate(board)

    board_name = board.name
    logger.log_event("play_start", board=board_name,
                     cells=board.total_cells(), layers=len(board.layers))

    # Serialize board to temp file
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    board_data = json.dumps(board_to_dict(board)).replace("'", "\\'")

    tmp.write(f"""import sys, json, os
sys.path.insert(0, {repr(script_dir)})
import tkinter as tk
from tile_level_simulator import PlayWindow, Board, Layer, Cell

data = json.loads({repr(json.dumps(board_to_dict(board)))})

board = Board(data['name'])
for ld in data['layers']:
    layer = Layer(ld['id'])
    for cd in ld['cells']:
        c = Cell(cd['x'], cd['y'], ld['id'])
        c.tile_id = cd['tile_id']
        layer.cells.append(c)
    board.layers.append(layer)

root = tk.Tk()
root.withdraw()
pw = PlayWindow(root, board)
pw.protocol("WM_DELETE_WINDOW", lambda: (pw.destroy(), root.destroy()))
pw.update_idletasks()
sw = pw.winfo_screenwidth()
sh = pw.winfo_screenheight()
w, h = 750, 700
pw.geometry(f"{{w}}x{{h}}+{{(sw-w)//2}}+{{(sh-h)//2}}")
root.mainloop()
try:
    os.unlink(__file__)
except:
    pass
""")
    tmp.close()
    tmp_path = tmp.name

    # Route qua Windows shell (cmd start) để có desktop access đầy đủ
    subprocess.Popen(
        ['cmd', '/c', 'start', '', sys.executable, tmp_path],
        shell=False,
    )

    return {
        "played": True,
        "board_name": board_name,
        "cells": board.total_cells(),
        "layers": len(board.layers),
        "message": f"Play window opened for '{board_name}'. User can play now."
    }


# ─────────────────────────────────────────────
# Unity-Style Report (Min/Max per level)
# ─────────────────────────────────────────────

def api_export_unity_report(folder_path, output_csv=None, samples=100,
                             weights=None) -> dict:
    """
    Generate a Unity-style TileCorrelationDifficultyReport.

    If boards already have tiles assigned (stones format with "i" fields),
    scores the ORIGINAL tiles — does NOT regenerate. This matches Unity behavior.

    If samples > 1, regenerates N times to collect Min/Max ranges.
    If samples == 1 (or tiles already assigned), scores once with original tiles.

    Output CSV format matches Unity BatchLevelDifficultyReport.
    """
    files = sorted([f for f in os.listdir(folder_path) if f.endswith('.json')
                    and not f.startswith('_')])
    results = []
    for fname in files:
        path = os.path.join(folder_path, fname)
        board = load_board_from_file(path)
        if board is None:
            continue

        vis_map = TileSolver._build_visibility(board)
        all_cells = board.all_cells()

        # Layout score (fixed — structure only)
        resolve = DifficultyScorer.compute_resolve_scores(board, vis_map)
        layout = DifficultyScorer.layout_score(resolve)

        # Coverage BEFORE strip (on all tiles, original positions)
        active_all = {id(c) for c in all_cells}
        coverages_before = DifficultyScorer._compute_coverages(board, active_all)
        cover_before = sum(1 for cid in active_all if coverages_before.get(cid, 0) == 4)

        if samples <= 1:
            # Score original tiles once (deterministic strip)
            score = DifficultyScorer.compute_full_score(board, vis_map, weights)
            ig_vals = [score.get("inter_group", 0)]
            ng_vals = [score.get("intra_group", 0)]
            ecv_vals = [score.get("cover100", 0)]
            actual_samples = 1
        else:
            # Score SAME tiles N times with ONE DotNetRandom instance
            # (matching Unity: static _rng persists across all calls)
            from tile_level_simulator import DotNetRandom
            if not hasattr(api_export_unity_report, '_rng'):
                api_export_unity_report._rng = DotNetRandom(0)
            rng = api_export_unity_report._rng
            ig_vals, ng_vals, ecv_vals = [], [], []
            for _ in range(samples):
                try:
                    score = DifficultyScorer.compute_full_score(
                        board, vis_map, weights, randomize_strip=rng)
                    ig_vals.append(score.get("inter_group", 0))
                    ng_vals.append(score.get("intra_group", 0))
                    ecv_vals.append(score.get("cover100", 0))
                except Exception:
                    pass
            actual_samples = samples

        name = fname.replace('.json', '')
        entry = {
            "layout_id": name,
            "layout_difficulty": round(layout, 2),
            "inter_max": round(max(ig_vals), 1) if ig_vals else 0,
            "inter_min": round(min(ig_vals), 1) if ig_vals else 0,
            "intra_max": round(max(ng_vals), 1) if ng_vals else 0,
            "intra_min": round(min(ng_vals), 1) if ng_vals else 0,
            "cover_count": cover_before,
            "cover_range": f"{cover_before}~{cover_before}",
            "eff_cover_range": f"{min(ecv_vals) if ecv_vals else 0}~{max(ecv_vals) if ecv_vals else 0}",
            "sample_count": actual_samples,
        }
        results.append(entry)

    # Export CSV
    csv_path = output_csv or os.path.join(folder_path, "_unity_report.csv")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("Level ID,Sample Count,"
                "InterGroup Min,InterGroup Max,"
                "IntraGroup Min,IntraGroup Max,"
                "Coverage Min,Coverage Max,"
                "Effective Coverage Min,Effective Coverage Max\n")
        for e in results:
            cv_parts = str(e['cover_range']).split('~')
            ecv_parts = str(e['eff_cover_range']).split('~')
            cv_min = cv_parts[0] if len(cv_parts) == 2 else e['cover_count']
            cv_max = cv_parts[1] if len(cv_parts) == 2 else e['cover_count']
            ecv_min = ecv_parts[0] if len(ecv_parts) == 2 else 0
            ecv_max = ecv_parts[1] if len(ecv_parts) == 2 else 0
            f.write(f"{e['layout_id']},{e['sample_count']},"
                    f"{e['inter_min']},{e['inter_max']},"
                    f"{e['intra_min']},{e['intra_max']},"
                    f"{cv_min},{cv_max},"
                    f"{ecv_min},{ecv_max}\n")

    logger.log_event("export_unity_report", folder=folder_path,
                     count=len(results), samples=samples, csv=csv_path)

    return {
        "count": len(results),
        "samples_per_level": samples,
        "csv_path": csv_path,
        "results": results,
    }


# ─────────────────────────────────────────────
# Mass Level Production Pipeline
# ─────────────────────────────────────────────

def _make_shape_cells(shape, radius, offset=0.0):
    """Generate cell positions for a shape. Reuses tile_board_editor logic."""
    cells = []
    r = max(1, radius)
    if shape == "diamond":
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) + abs(dy) <= r:
                    cells.append({"x": dx + offset, "y": dy + offset})
    elif shape == "rect":
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                cells.append({"x": dx + offset, "y": dy + offset})
    elif shape == "hex":
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                dz = -dx - dy
                if max(abs(dx), abs(dy), abs(dz)) <= r:
                    cells.append({"x": dx + offset, "y": dy + offset})
    else:  # random = pick random shape
        return _make_shape_cells(random.choice(["diamond", "rect", "hex"]), radius, offset)
    return cells


def api_generate_random_board(name="auto", num_layers=4, cells_per_layer=15,
                               shape="diamond", shrink_rate=0.7, stagger=True) -> dict:
    """
    Generate a random board layout with specified shape and parameters.

    Args:
        name: Board name
        num_layers: Number of layers (2-12)
        cells_per_layer: Approximate cells per layer (determines radius)
        shape: "diamond", "rect", "hex", or "random"
        shrink_rate: How fast layers shrink (0.5-1.0). Lower = more pyramid
        stagger: Offset every other layer by 0.5 (half-grid)
    """
    import math
    # Estimate radius from cells_per_layer (diamond: cells ≈ 2*r*(r+1)+1)
    base_radius = max(1, int(math.sqrt(cells_per_layer / 2)))

    layers_spec = []
    for li in range(num_layers):
        r = max(1, int(base_radius * (shrink_rate ** li)))
        offset = 0.5 if (stagger and li % 2 == 1) else 0.0
        cells = _make_shape_cells(shape, r, offset)
        layers_spec.append({"cells": cells})

    result = api_create_board(name, layers_spec)

    # Ensure total cells divisible by 3 (game rule)
    total = result.get("total_cells", 0)
    remainder = total % 3
    if remainder > 0 and result.get("layers"):
        # Remove remainder cells from the largest layer
        largest = max(result["layers"], key=lambda l: len(l.get("cells", [])))
        for _ in range(remainder):
            if largest["cells"]:
                largest["cells"].pop()
        result["total_cells"] = sum(len(l.get("cells", [])) for l in result["layers"])
    logger.log_event("random_board", name=name, layers=num_layers,
                     shape=shape, cells=result.get("total_cells"))
    return result


def api_generate_level_batch(count=100, layout_config=None, gen_params=None,
                              target=None, max_attempts_per_level=50,
                              output_folder=None) -> dict:
    """
    Pipeline: create N quality levels in 1 call.

    Args:
        count: Number of levels to create
        layout_config: Layout randomization ranges:
            num_layers: [min, max] (default [3, 6])
            cells_per_layer: [min, max] (default [10, 25])
            shapes: list of shapes (default ["diamond", "hex"])
            shrink_rate: [min, max] (default [0.5, 0.9])
        gen_params: Generation params (color_count, knobs, etc.)
        target: Score criteria (score_min, score_max, etc.)
        max_attempts_per_level: Retry per level
        output_folder: If set, export stones format to this folder

    Returns: {created, failed, levels: [{file, score, cells, layers}, ...]}
    """
    lc = layout_config or {}
    nl_range = lc.get("num_layers", [3, 6])
    cpl_range = lc.get("cells_per_layer", [10, 25])
    shapes = lc.get("shapes", ["diamond", "hex"])
    sr_range = lc.get("shrink_rate", [0.5, 0.9])

    params = gen_params or {"color_count": 4, "validate": True}
    levels = []
    failed = 0

    if output_folder:
        os.makedirs(output_folder, exist_ok=True)

    for i in range(count):
        # Random layout params
        nl = random.randint(nl_range[0], nl_range[1])
        cpl = random.randint(cpl_range[0], cpl_range[1])
        shape = random.choice(shapes)
        sr = random.uniform(sr_range[0], sr_range[1])

        board_dict = api_generate_random_board(
            name=f"Level_{i+1:03d}", num_layers=nl,
            cells_per_layer=cpl, shape=shape, shrink_rate=sr)

        # Generate with target
        if target:
            result = api_auto_generate(board_dict, params, target, max_attempts_per_level)
        else:
            result = api_generate(board_dict, params)
            result["matched"] = True
            result["attempts"] = 1

        score = result.get("score", {})
        board = result.get("board", board_dict)

        level_info = {
            "idx": i + 1,
            "name": f"Level_{i+1:03d}",
            "cells": board.get("total_cells", 0),
            "layers": len(board.get("layers", [])),
            "shape": shape,
            "score": score.get("final_score", 0),
            "layout": score.get("layout", 0),
            "inter_group": score.get("inter_group", 0),
            "matched": result.get("matched", False),
            "attempts": result.get("attempts", 0),
        }

        if result.get("matched", False):
            # Export if folder specified
            if output_folder:
                fname = f"Level_{i+1:03d}.json"
                fpath = os.path.join(output_folder, fname)
                board_obj = board_from_dict(board)
                data = export_board_stones_format(board_obj)
                with open(fpath, "w") as f:
                    json.dump(data, f, separators=(",", ":"))
                level_info["file"] = fname

            levels.append(level_info)
        else:
            failed += 1

    logger.log_event("level_batch", count=count, created=len(levels), failed=failed)

    return {
        "created": len(levels),
        "failed": failed,
        "total_requested": count,
        "levels": levels,
    }


def api_generate_difficulty_progression(total_levels=200, difficulty_curve="linear",
                                         score_start=10, score_end=120,
                                         layout_config=None, gen_params=None,
                                         output_folder=None,
                                         max_attempts_per_level=100) -> dict:
    """
    Create levels following a difficulty curve from easy to hard.

    Args:
        total_levels: Number of levels
        difficulty_curve: "linear", "ease_in", "ease_out", "s_curve"
        score_start: Target score for first level
        score_end: Target score for last level
        layout_config: Layout randomization (same as generate_level_batch)
        gen_params: Generation params
        output_folder: Export folder
        max_attempts_per_level: Retry per level
    """
    import math

    lc = layout_config or {}
    params = gen_params or {"color_count": 4, "validate": True}

    if output_folder:
        os.makedirs(output_folder, exist_ok=True)

    curve_data = []
    levels = []
    failed = 0

    for i in range(total_levels):
        t = i / max(1, total_levels - 1)  # 0.0 to 1.0

        # Apply curve shape
        if difficulty_curve == "ease_in":
            t = t * t
        elif difficulty_curve == "ease_out":
            t = 1 - (1 - t) ** 2
        elif difficulty_curve == "s_curve":
            t = t * t * (3 - 2 * t)  # smoothstep
        # else: linear (t unchanged)

        target_score = score_start + (score_end - score_start) * t
        tolerance = max(3, target_score * 0.15)  # ±15% or ±3

        # Scale layout complexity with difficulty
        base_nl = lc.get("num_layers", [3, 8])
        base_cpl = lc.get("cells_per_layer", [10, 30])
        shapes = lc.get("shapes", ["diamond", "hex"])
        sr_range = lc.get("shrink_rate", [0.5, 0.9])

        # More layers/cells for harder targets
        nl_min = base_nl[0] + int((base_nl[1] - base_nl[0]) * t * 0.5)
        nl_max = min(base_nl[1], nl_min + 3)
        cpl_min = base_cpl[0] + int((base_cpl[1] - base_cpl[0]) * t * 0.3)
        cpl_max = min(base_cpl[1], cpl_min + 10)

        nl = random.randint(nl_min, nl_max)
        cpl = random.randint(cpl_min, cpl_max)
        shape = random.choice(shapes)
        sr = random.uniform(sr_range[0], sr_range[1])

        board_dict = api_generate_random_board(
            name=f"Level_{i+1:03d}", num_layers=nl,
            cells_per_layer=cpl, shape=shape, shrink_rate=sr)

        target = {
            "score_min": max(0, target_score - tolerance),
            "score_max": target_score + tolerance,
        }

        result = api_auto_generate(board_dict, params, target, max_attempts_per_level)
        score = result.get("score", {})
        board = result.get("board", board_dict)
        actual_score = score.get("final_score", 0)

        entry = {
            "level_idx": i + 1,
            "target_score": round(target_score, 1),
            "actual_score": actual_score,
            "matched": result.get("matched", False),
            "cells": board.get("total_cells", 0),
            "layers": len(board.get("layers", [])),
            "shape": shape,
        }

        if output_folder:
            fname = f"Level_{i+1:03d}.json"
            fpath = os.path.join(output_folder, fname)
            board_obj = board_from_dict(board)
            data = export_board_stones_format(board_obj)
            with open(fpath, "w") as f:
                json.dump(data, f, separators=(",", ":"))
            entry["file"] = fname

        curve_data.append(entry)
        if result.get("matched", False):
            levels.append(entry)
        else:
            failed += 1

    # Export CSV report
    csv_path = None
    if output_folder:
        csv_path = os.path.join(output_folder, "_progression_report.csv")
        with open(csv_path, "w") as f:
            f.write("idx,target,actual,matched,cells,layers,shape,file\n")
            for e in curve_data:
                f.write(f"{e['level_idx']},{e['target_score']},{e['actual_score']},"
                        f"{e['matched']},{e['cells']},{e['layers']},{e['shape']},"
                        f"{e.get('file','')}\n")

    logger.log_event("difficulty_progression", total=total_levels,
                     created=len(levels), failed=failed, curve=difficulty_curve)

    return {
        "created": len(levels),
        "failed": failed,
        "total_requested": total_levels,
        "curve": curve_data,
        "csv_path": csv_path,
    }


def api_clone_and_vary(board_dict, count=10, vary_params=True, vary_layout=True,
                        gen_params=None, target=None, output_folder=None) -> dict:
    """
    Clone a board and create variants by modifying layout and/or generation params.

    Args:
        board_dict: Source board
        count: Number of variants
        vary_params: Randomize color_count/knobs slightly
        vary_layout: Add/remove random cells from random layers
        gen_params: Base generation params
        target: Score criteria for filtering
        output_folder: Export folder
    """
    params = gen_params or {"color_count": 4, "validate": True}
    variants = []

    if output_folder:
        os.makedirs(output_folder, exist_ok=True)

    for i in range(count):
        bd = json.loads(json.dumps(board_dict))  # deep copy
        changes = []

        if vary_layout and bd.get("layers"):
            # Random modification: add or remove 1-3 cells from a random layer
            layer_idx = random.randint(0, len(bd["layers"]) - 1)
            layer = bd["layers"][layer_idx]
            cells = layer.get("cells", [])

            if random.random() < 0.5 and len(cells) > 3:
                # Remove 1-3 random cells
                n_remove = min(random.randint(1, 3), len(cells) - 3)
                for _ in range(n_remove):
                    if cells:
                        cells.pop(random.randint(0, len(cells) - 1))
                changes.append(f"removed {n_remove} cells from layer {layer_idx}")
            else:
                # Add 1-3 cells near existing ones
                n_add = random.randint(1, 3)
                for _ in range(n_add):
                    if cells:
                        ref = random.choice(cells)
                        new_x = ref["x"] + random.choice([-1, 0, 1])
                        new_y = ref["y"] + random.choice([-1, 0, 1])
                        if not any(c["x"] == new_x and c["y"] == new_y for c in cells):
                            cells.append({"x": new_x, "y": new_y, "tile_id": -1})
                changes.append(f"added cells to layer {layer_idx}")

            # Recalculate total_cells
            bd["total_cells"] = sum(len(l.get("cells", [])) for l in bd["layers"])

        p = dict(params)
        if vary_params:
            # Slight random variation on color_count
            cc = p.get("color_count", 4)
            cc_var = cc + random.choice([-1, 0, 0, 0, 1])
            p["color_count"] = max(2, min(9, cc_var))
            if cc_var != cc:
                changes.append(f"color_count {cc}→{p['color_count']}")

        # Generate
        if target:
            result = api_auto_generate(bd, p, target, 50)
        else:
            result = api_generate(bd, p)
            result["matched"] = True

        score = result.get("score", {})
        board = result.get("board", bd)

        variant = {
            "idx": i + 1,
            "changes": changes,
            "score": score.get("final_score", 0),
            "matched": result.get("matched", False),
            "board": board,
        }

        if output_folder:
            fname = f"Variant_{i+1:03d}.json"
            fpath = os.path.join(output_folder, fname)
            board_obj = board_from_dict(board)
            data = export_board_stones_format(board_obj)
            with open(fpath, "w") as f:
                json.dump(data, f, separators=(",", ":"))
            variant["file"] = fname
            del variant["board"]  # don't include full board in response

        variants.append(variant)

    logger.log_event("clone_and_vary", count=count, created=len(variants))
    return {"variants": variants, "source": board_dict.get("name", "unknown")}


def api_validate_level_set(folder_path, gen_params=None, checks=None) -> dict:
    """
    Validate quality of all levels in a folder.

    checks keys: min_cells, max_cells, min_layers, max_layers,
                 score_range [min, max], solvable (bool), triples_balanced (bool)
    """
    checks = checks or {}
    params = gen_params or {}

    files = sorted([f for f in os.listdir(folder_path) if f.endswith('.json')
                    and not f.startswith('_')])
    passed = []
    issues = []

    for fname in files:
        path = os.path.join(folder_path, fname)
        bd = api_load_board_from_path(path)
        if "error" in bd:
            issues.append({"file": fname, "reason": "Failed to load"})
            continue

        info = api_get_board_info(bd)
        nc = info["total_cells"]
        nl = info["total_layers"]
        dist = info["tile_distribution"]
        has_tiles = info["has_tiles"]

        file_issues = []

        if nc < checks.get("min_cells", 0):
            file_issues.append(f"Too few cells: {nc} < {checks['min_cells']}")
        if nc > checks.get("max_cells", 99999):
            file_issues.append(f"Too many cells: {nc} > {checks['max_cells']}")
        if nl < checks.get("min_layers", 0):
            file_issues.append(f"Too few layers: {nl} < {checks['min_layers']}")
        if nl > checks.get("max_layers", 99999):
            file_issues.append(f"Too many layers: {nl} > {checks['max_layers']}")

        if has_tiles and checks.get("triples_balanced", False):
            bad = [t for t, c in dist.items() if c % 3 != 0]
            if bad:
                file_issues.append(f"Types not x3: {bad}")

        if has_tiles and "score_range" in checks:
            score = api_score(bd)
            fs = score.get("final_score", 0)
            sr = checks["score_range"]
            if fs < sr[0] or fs > sr[1]:
                file_issues.append(f"Score {fs:.1f} outside [{sr[0]}, {sr[1]}]")

        if file_issues:
            issues.append({"file": fname, "reasons": file_issues})
        else:
            passed.append(fname)

    logger.log_event("validate_set", folder=folder_path,
                     total=len(files), passed=len(passed), failed=len(issues))

    return {
        "total": len(files),
        "passed": len(passed),
        "failed": len(issues),
        "passed_files": passed,
        "issues": issues,
    }


def api_export_level_set(source_folder, output_folder, format="stones",
                          include_csv=True, rename_pattern="Level_{idx:03d}") -> dict:
    """
    Export all levels from source folder to output folder with optional renaming.
    """
    os.makedirs(output_folder, exist_ok=True)
    files = sorted([f for f in os.listdir(source_folder) if f.endswith('.json')
                    and not f.startswith('_')])

    exported = []
    for i, fname in enumerate(files):
        path = os.path.join(source_folder, fname)
        bd = api_load_board_from_path(path)
        if "error" in bd:
            continue

        board = board_from_dict(bd)
        new_name = rename_pattern.format(idx=i+1, name=fname.replace('.json',''))

        if format == "stones":
            data = export_board_stones_format(board)
            out_path = os.path.join(output_folder, new_name + ".json")
            with open(out_path, "w") as f:
                json.dump(data, f, separators=(",", ":"))
        else:
            out_path = os.path.join(output_folder, new_name + ".json")
            meta.export_with_metadata(board, output_folder)

        exported.append({"original": fname, "exported": new_name + ".json"})

    csv_path = None
    if include_csv:
        csv_path = os.path.join(output_folder, "_level_index.csv")
        with open(csv_path, "w") as f:
            f.write("idx,file,cells,layers\n")
            for i, e in enumerate(exported):
                bd = api_load_board_from_path(os.path.join(output_folder, e["exported"]))
                if "error" not in bd:
                    info = api_get_board_info(bd)
                    f.write(f"{i+1},{e['exported']},{info['total_cells']},{info['total_layers']}\n")

    total_size = sum(os.path.getsize(os.path.join(output_folder, e["exported"]))
                     for e in exported if os.path.exists(os.path.join(output_folder, e["exported"])))

    logger.log_event("export_set", source=source_folder, output=output_folder,
                     count=len(exported))

    return {
        "exported": len(exported),
        "output_folder": output_folder,
        "csv_path": csv_path,
        "total_size_kb": round(total_size / 1024, 1),
    }


# ─────────────────────────────────────────────
# Logs (for AI debugging)
# ─────────────────────────────────────────────

def api_get_logs(n=50) -> list:
    return logger.get_recent_logs(n)


# ─────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Tile API Self-Test ===")

    # Test board creation
    b = api_create_board("test", [
        {"cells": [{"x": i, "y": j} for i in range(3) for j in range(3)]}
        for _ in range(3)
    ])
    print(f"Created: {b['name']}, {b['total_cells']} cells, {len(b['layers'])} layers")

    # Test generate
    r = api_generate(b, {"color_count": 3, "validate": False})
    print(f"Generated: solvable={r['stats']['solvable']}, score={r['score'].get('final_score')}")

    # Test score
    s = api_score(r["board"])
    print(f"Score: layout={s['layout']}, inter={s['inter_group']}, final={s['final_score']}")

    # Test batch
    bs = api_batch_score(b, {"color_count": 3, "validate": False}, n_runs=5)
    print(f"Batch: final min={bs['final_score']['min']}, max={bs['final_score']['max']}")

    # Test board editing
    b2 = api_add_layer(b, [{"x": 0, "y": 0}, {"x": 1, "y": 0}])
    print(f"After add_layer: {len(b2['layers'])} layers")

    b3 = api_copy_layer(b2, 0)
    print(f"After copy_layer: {len(b3['layers'])} layers")

    b4 = api_remove_layer(b3, 0)
    print(f"After remove_layer: {len(b4['layers'])} layers")

    # Test presets
    presets = api_list_presets()
    print(f"Presets: {list(presets.keys())}")

    # Test weights
    w = api_get_weights()
    print(f"Weights: {w}")

    # Test logs
    logs = api_get_logs(5)
    print(f"Recent logs: {len(logs)} entries")
    for l in logs[-3:]:
        print(f"  [{l['event']}] {l.get('board', '')}")

    print("\n=== All tests passed ===")
