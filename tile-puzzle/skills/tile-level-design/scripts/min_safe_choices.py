"""min_safe_choices — the "one wrong move = instant loss" difficulty probe (plugin-distributed).

Raw winning-path counts almost always come out huge for any real board (independent tiles elsewhere
can be picked in any order), so they say nothing about how forgiving the OPENING is. What a player feels
as "only one way to play this" is a BOTTLENECK: at some early step, among the currently-pickable tiles,
only one choice avoids walking into a guaranteed loss. `min_safe_choices` walks the first `check_depth`
steps of a proven winning path and, at each step, counts how many currently-pickable moves are still
"safe" (lead to a winnable state). `min_safe_count == 1` while `total_pickable > 1` is the bottleneck.

The safety test is an EXACT existence oracle `winnable(active, tray)` carrying TWO verified-exact
optimizations that do NOT alter the search tree (it explores the SAME exhaustive DFS, only cheaper/node):
  (1) tsize threading      — carry the running tray size instead of re-summing the packed tray each node.
  (2) incremental pickable — thread the pickable mask, re-test only the tiles a pick uncovers.

NO atomic-triple collapse of any kind. Every triple-forcing collapse — solve_v3's full atomic AND the
"narrow" `== needed` variant — is UNSOUND here: it commits to completing a triple first and short-circuits,
which can miss a win that must start with a different type (over-prune → wrongly reports a safe move as a
trap → wrong difficulty label). This was caught empirically by a PYTHONHASHSEED sweep on
`NewLayout_L20/cc12/s1` after limited board-set gating had (misleadingly) passed. Do not re-add a collapse.

~1.8x over the tsize-threaded form alone (itself ~2x over a plain re-summing DFS). `count_wins_capped`
(path COUNT) gets tsize threading only — anything that reorders/merges picks would corrupt the count.

Programmatic:
    from min_safe_choices import min_safe_choices, count_wins_capped
    board = load_board_from_file(path)                 # ABSOLUTE path
    info = min_safe_choices(board, check_depth=3)       # -> (min_safe, step_at_min, total_pickable) | None
    # Pass blocked_by=<your own bb> to reuse a caller-specific visibility; default builds the standard
    # 1x1-box blocked_by (identical to solve_with_path / verify_smart_v3).
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
from verify_smart_v3 import build_bitmask_visibility  # (blocked_by, blocks), 1x1 box
from solve_path import solve_with_path

TRAY_SIZE = 7


def _reject_specials(cells):
    """min_safe_choices / count_wins_capped model NORMAL match-3 boards only. A board carrying special
    tiles (i >= 1000: BONUS 1001 / MISSION 1002) would be treated here as ordinary match-3 tiles (wrong —
    specials AUTO-CLEAR, they are not trayed) and would blow `n_types` up to ~1002. Solvability for such
    boards is `solve_special.solve_v3_special`; there is no meaningful min_safe probe for them."""
    if any(getattr(c, "tile_id", 0) >= 1000 for c in cells):
        raise ValueError(
            "min_safe_choices/count_wins_capped are for NORMAL boards only; this board has special tiles "
            "(i>=1000). Specials auto-clear and must be handled by solve_special.solve_v3_special, not "
            "treated as match-3 here.")


def _engine(cells, blocked_by=None):
    """Build the winnable/count_wins closures + tray helpers for a fixed cell set.

    blocked_by: optional caller-supplied blocked_by bitmask list (bb[i] = tiles that cover i). When None,
    the standard 1x1-box visibility is built. `blocks` (the transpose: tiles that i covers) is taken from
    build_bitmask_visibility, or derived by transposing a supplied blocked_by."""
    n = len(cells)
    tile_ids = [c.tile_id for c in cells]
    n_types = (max(tile_ids) + 1) if tile_ids else 1
    if blocked_by is None:
        bb, blocks = build_bitmask_visibility(cells)
    else:
        bb = blocked_by
        blocks = [0] * n
        for i in range(n):
            b = bb[i]
            while b:
                low = b & -b
                j = low.bit_length() - 1
                b ^= low
                blocks[j] |= (1 << i)

    def tray_count(tray, t): return (tray >> (t * 2)) & 3
    def tray_add(tray, t):   return tray + (1 << (t * 2))
    def tray_sub3(tray, t):  return tray - (3 << (t * 2))
    def tray_size(tray):
        s = 0
        for t in range(n_types):
            s += (tray >> (t * 2)) & 3
        return s

    def compute_pickable(active):
        p, a = 0, active
        while a:
            low = a & -a
            i = low.bit_length() - 1
            if not (bb[i] & active):
                p |= low
            a ^= low
        return p

    def _expose(P, i, na):
        """Incremental compute_pickable: removing tile i can only newly EXPOSE tiles it covered
        (blocks[i]); nothing already pickable becomes un-pickable. O(|blocks[i]|) vs O(active)."""
        nP = P & ~(1 << i)
        cand = blocks[i] & na
        while cand:
            b = cand & -cand
            j = b.bit_length() - 1
            cand ^= b
            if not (bb[j] & na):
                nP |= b
        return nP

    sys.setrecursionlimit(max(sys.getrecursionlimit(), n + 500))

    # ---- EXISTENCE oracle: variant C (tsize threading + incremental pickable). EXACT by construction:
    # it explores the SAME exhaustive branch tree as a plain DFS, only cheaper per node. NO atomic collapse
    # of any kind — every triple-forcing collapse (full solve_v3 atomic AND the narrow `== needed` form)
    # is UNSOUND for this arbitrary-mid-state existence query: it commits to a triple-first and
    # short-circuits, which can miss a win that starts with a different type. Proven over-prune (a
    # hash-seed sweep caught the narrow form on NewLayout_L20/cc12/s1). DO NOT re-add any collapse here.
    win_memo = {}

    def winnable(active, tray):
        return _winnable(active, tray, tray_size(tray), compute_pickable(active))

    def _winnable(active, tray, tsize, P):
        if active == 0:
            return True
        key = (active, tray)
        if key in win_memo:
            return win_memo[key]
        if P == 0:
            win_memo[key] = False
            return False
        p = P
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                nt = tray_sub3(tray_add(tray, tid), tid)
                nts = tsize - 2
            else:
                if (tsize + 1) >= TRAY_SIZE:
                    continue
                nt = tray_add(tray, tid)
                nts = tsize + 1
            na = active ^ low
            if _winnable(na, nt, nts, _expose(P, i, na)):
                win_memo[key] = True
                return True
        win_memo[key] = False
        return False

    # ---- path COUNT (capped): tsize threading ONLY — narrow atomic would corrupt the count ----
    cnt_memo = {}

    def count_wins(active, tray, cap):
        return _count_wins(active, tray, tray_size(tray), cap)

    def _count_wins(active, tray, tsize, cap):
        if active == 0:
            return 1
        key = (active, tray)
        if key in cnt_memo:
            return cnt_memo[key]
        pickable = compute_pickable(active)
        if pickable == 0:
            cnt_memo[key] = 0
            return 0
        total, p = 0, pickable
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                nt = tray_sub3(tray_add(tray, tid), tid)
                nts = tsize - 2
            else:
                if (tsize + 1) >= TRAY_SIZE:
                    continue
                nt = tray_add(tray, tid)
                nts = tsize + 1
            total += _count_wins(active ^ low, nt, nts, cap)
            if total >= cap:
                total = cap
                break
        cnt_memo[key] = min(total, cap)
        return cnt_memo[key]

    return dict(n=n, tile_ids=tile_ids, tray_count=tray_count, tray_add=tray_add,
                tray_sub3=tray_sub3, tray_size=tray_size, compute_pickable=compute_pickable,
                winnable=winnable, count_wins=count_wins)


def min_safe_choices(board, check_depth=3, path_cap=500_000, blocked_by=None):
    """Returns (min_safe_count, step_at_min, total_pickable_at_that_step), or None if unsolvable.
    `min_safe_count == 1` while `total_pickable > 1` at that step is the bottleneck.
    NORMAL boards only (raises ValueError on boards with special tiles i>=1000 — see _reject_specials)."""
    _reject_specials(board.all_cells())
    result, picks, _elapsed, cells = solve_with_path(board, max_expansions=path_cap)
    if result is not True or not picks:
        return None
    e = _engine(cells, blocked_by)
    n = e["n"]; tile_ids = e["tile_ids"]
    tray_count = e["tray_count"]; tray_add = e["tray_add"]; tray_sub3 = e["tray_sub3"]
    tray_size = e["tray_size"]; compute_pickable = e["compute_pickable"]; winnable = e["winnable"]

    active, tray = (1 << n) - 1, 0
    worst = None
    for step_idx, idx in enumerate(picks[:check_depth]):
        pickable = compute_pickable(active)
        total_pick, safe, p = 0, 0, pickable
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            total_pick += 1
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                nt = tray_sub3(tray_add(tray, tid), tid)
            else:
                if (tray_size(tray) + 1) >= TRAY_SIZE:
                    continue          # this move is itself a loss, not a safe choice
                nt = tray_add(tray, tid)
            if winnable(active ^ low, nt):
                safe += 1
        if worst is None or safe < worst[0]:
            worst = (safe, step_idx + 1, total_pick)

        tid = tile_ids[idx]
        tc = tray_count(tray, tid)
        tray = tray_sub3(tray_add(tray, tid), tid) if tc == 2 else tray_add(tray, tid)
        active ^= (1 << idx)
    return worst


def count_wins_capped(board, cap=2, path_cap=500_000, blocked_by=None):
    """Number of distinct winning full paths, capped at `cap` (returns as soon as `cap` is reached).
    None if unsolvable. Uses tsize threading only (exact for counting). NORMAL boards only.
    Signature matches the project's original `count_wins_capped(board, cap=2)`."""
    _reject_specials(board.all_cells())
    result, picks, _elapsed, cells = solve_with_path(board, max_expansions=path_cap)
    if result is not True or not picks:
        return None
    e = _engine(cells, blocked_by)
    return e["count_wins"]((1 << e["n"]) - 1, 0, cap)


if __name__ == "__main__":
    # CLI: python min_safe_choices.py <level.json> [check_depth]   (machine-readable one-line output)
    import json
    from tile_level_simulator import load_board_from_file
    if len(sys.argv) < 2:
        raise SystemExit("usage: python min_safe_choices.py <level.json> [check_depth]")
    p = os.path.abspath(sys.argv[1])
    cd = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    board = load_board_from_file(p)
    if board is None:
        raise SystemExit(f"could not load board from {p}")
    try:
        info = min_safe_choices(board, check_depth=cd)
    except ValueError as ex:
        print(f"{os.path.basename(p)}: N/A ({ex})")
        raise SystemExit(0)
    if info is None:
        print(f"{os.path.basename(p)}: unsolvable")
    else:
        safe, step, total = info
        print(f"{os.path.basename(p)}: min_safe={safe} step={step} total_pickable={total} "
              f"bottleneck={'YES' if (safe <= 1 and total > 1) else 'no'}")
