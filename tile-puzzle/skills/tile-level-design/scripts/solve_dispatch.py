"""solve_any -- dispatch to the correct exact solver based on whether a board carries special tiles.

Two solvers exist and neither is a safe default for both cases:
  - verify_smart_v3.solve_v3        -- NORMAL boards. Does NOT understand bonus/mission auto-clear
                                        semantics; calling it on a board WITH specials silently
                                        mis-verifies solvability.
  - solve_special.solve_v3_special  -- REQUIRED whenever any stone has i>=1000 (bonus 1001 / mission
                                        1002); footprint-aware auto-clear cascade.

Calling the wrong one for a given board is easy to do silently -- there was no guard forcing the right
choice (Task 2d). solve_any() removes the need to know which one to call: new code that isn't already
certain of its board type should default to this. Existing direct solve_v3 / solve_v3_special call
sites that already know their board type are UNCHANGED -- this is additive, not a migration.

Usage:
    from solve_dispatch import solve_any
    status, depth, expansions = solve_any(board, max_expansions=200_000)
    # same (status, best_depth, expansions) contract as solve_v3 / solve_v3_special.
"""
import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
sys.path.insert(0, HERE)
from verify_smart_v3 import solve_v3  # noqa: E402


def solve_any(board, max_expansions=None, verbose=False, special_halves=None):
    """Same (status, best_depth, expansions) contract as solve_v3. Inspects the board for any stone
    with tile_id >= 1000 (bonus/mission) and dispatches to solve_special.solve_v3_special when found,
    else solve_v3. Import of solve_special is deferred (not module-level) to avoid a circular import --
    solve_special.py itself imports from verify_smart_v3.py."""
    from solve_special import solve_v3_special  # noqa: E402 (deferred: avoids import cycle)
    has_special = any(c.tile_id >= 1000 for c in board.all_cells())
    if has_special:
        return solve_v3_special(board, special_ids=(1001, 1002), max_expansions=max_expansions,
                                verbose=verbose, special_halves=special_halves)
    return solve_v3(board, max_expansions=max_expansions, verbose=verbose)
