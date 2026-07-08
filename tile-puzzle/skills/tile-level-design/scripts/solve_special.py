"""v3 DFS solver EXTENDED with special auto-clear — the RIGOROUS solvability check for levels that
contain bonus (1001) / mission (1002) tiles.

A special tile is NOT match-3: it AUTO-CLEARS the moment it is uncovered (no tray, no triple). So at
every search node we first cascade-remove all currently-exposed special cells for free (which may
expose more cells — normal or special), then run the normal match-3 DFS over the remaining tiles.
Win = every cell cleared (normal via triples, special via auto-clear). This keeps the special cells'
COVER effect in the board (unlike the 0.3.0 shortcut that excluded them), so it is sound.

Mirrors verify_smart_v3.solve_v3 (atomic-triple collapse + transposition table + cap) and returns the
same (status, best_depth, expansions). The engine file is left byte-identical (parity); this lives in
the skill's scripts/.

Usage (programmatic):
    from solve_special import solve_v3_special, special_halves_from_level
    import json
    data = json.load(open(path, encoding="utf-8"))
    board = load_board_from_file(path)                       # ABSOLUTE path
    halves = special_halves_from_level(data)                 # <-- REQUIRED so 3×3 specials solve as 3×3
    status, depth, exp = solve_v3_special(board, special_ids=(1001, 1002),
                                          max_expansions=2_000_000, special_halves=halves)
    # (without `special_halves` every special is modelled as 2×2 — optimistic for 3×3 levels)
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
from verify_smart_v3 import build_bitmask_visibility  # noqa: F401  (kept for reduction cross-checks)

TRAY_SIZE = 7


def footprint_half(sid, s):
    """Special collision half-extent from its render `s` (2×2 → 1.0, 3×3 → 1.5).
    MISSION (1002): s = 0.7 → 2×2, s = 1.0 → 3×3  (threshold s ≥ 0.85 → 3×3).
    BONUS   (1001): s = 1.0 → 2×2, s = 1.5 → 3×3  (threshold s ≥ 1.25 → 3×3).
    None / unknown → 2×2 (half 1.0). Shared with make_play_html's JS `specHalf` and reserve_special."""
    if s is None:
        return 1.0
    if sid == 1001:
        return 1.5 if s >= 1.25 else 1.0
    return 1.5 if s >= 0.85 else 1.0


def special_halves_from_level(data, special_ids=(1001, 1002)):
    """Build the {(round(x,4), round(y,4), layer_idx): footprint_half} map from a level JSON's special
    stones (keyed to match the loaded board's cells), so solving a FILE directly models each special's
    true 2×2/3×3 footprint. Pass the result as `solve_v3_special(..., special_halves=<this>)`. Without
    it, `solve_v3_special` defaults every special to 2×2 (half 1.0) — OPTIMISTIC for 3×3 specials."""
    sset = set(special_ids)
    halves = {}
    for ly in data.get("layers", []):
        L = ly.get("index")
        for st in ly.get("stones", []):
            i = st.get("i")
            if i in sset:
                halves[(round(float(st["x"]), 4), round(float(st["y"]), 4), L)] = footprint_half(i, st.get("s"))
    return halves


def _build_visibility_2x2(cells, sset, special_halves=None):
    """Visibility with the special COLLISION model: a NORMAL tile is 1×1 (half 0.5); a SPECIAL is a
    2×2 (half 1.0) OR 3×3 (half 1.5) object. The per-special half comes from `special_halves` — a dict
    {(round(x,4), round(y,4), layer_idx): half} (built by the caller from each stone's `s` via
    footprint_half); any special not in the map defaults to 1.0 (2×2). An upper cell blocks a lower one
    iff their footprints overlap: |dx| < halfA+halfB & |dy| < halfA+halfB (partial overlap counts).
    normal↔normal = 1.0 (identical to the engine — no-special boards unchanged); a 2×2 special↔normal
    = 1.5, a 3×3 special↔normal = 2.0. Matches make_play_html's `halfOf`."""
    n = len(cells)
    blocked_by = [0] * n
    blocks = [0] * n
    def _hf(c):
        if c.tile_id not in sset:
            return 0.5
        if special_halves:
            return special_halves.get((round(c.x, 4), round(c.y, 4), c.layer_idx), 1.0)
        return 1.0
    half = [_hf(c) for c in cells]
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j:
                continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx:
                thr = half[i] + half[j]
                if abs(cj.x - ci.x) < thr and abs(cj.y - ci.y) < thr:
                    blocked_by[i] |= 1 << j
                    blocks[j] |= 1 << i
    return blocked_by, blocks


class _CapHit(Exception):
    pass


def solve_v3_special(board, special_ids=(1001, 1002), max_expansions=None, verbose=False, special_halves=None):
    cells = board.all_cells()
    n = len(cells)
    sset = set(special_ids)
    raw = [c.tile_id for c in cells]
    is_special = [1 if t in sset else 0 for t in raw]
    special_mask = 0
    for i in range(n):
        if is_special[i]:
            special_mask |= (1 << i)
    # normal types only feed the tray; specials get -1 (never trayed / branched)
    tile_ids = [(-1 if is_special[i] else raw[i]) for i in range(n)]
    norm = [t for t in tile_ids if t >= 0]
    n_types = (max(norm) + 1) if norm else 1
    blocked_by, blocks = _build_visibility_2x2(cells, sset, special_halves)   # specials collide as 2×2/3×3

    def tray_count(tray, t): return (tray >> (t * 2)) & 3
    def tray_add(tray, t):   return tray + (1 << (t * 2))
    def tray_sub3(tray, t):  return tray - (3 << (t * 2))
    def tray_size(tray):
        s = 0
        for t in range(n_types):
            s += (tray >> (t * 2)) & 3
        return s

    dead = set()
    stats = {"expansions": 0, "best_depth": 0}
    start = time.time()
    cap = max_expansions
    sys.setrecursionlimit(max(sys.getrecursionlimit(), n + 100))

    def compute_pickable(active):
        p = 0; a = active
        while a:
            low = a & -a
            i = low.bit_length() - 1
            if not (blocked_by[i] & active):
                p |= low
            a ^= low
        return p

    def auto_clear(active):
        """Remove every exposed special for free, cascading until none is pickable."""
        while special_mask & active:
            exposed = compute_pickable(active) & special_mask & active
            if not exposed:
                break
            active &= ~exposed
        return active

    def dfs(active, tray, depth):
        active = auto_clear(active)                      # specials clear for free first
        stats["expansions"] += 1
        if depth > stats["best_depth"]:
            stats["best_depth"] = depth
        if cap is not None and stats["expansions"] >= cap:
            raise _CapHit()
        if active == 0:
            return True
        key = (active, tray)
        if key in dead:
            return False
        pickable_mask = compute_pickable(active)
        if pickable_mask == 0:
            dead.add(key); return False

        # group pickable by NORMAL type (specials are auto-cleared, never branched)
        by_type = {}
        p = pickable_mask
        while p:
            low = p & -p; i = low.bit_length() - 1; p ^= low
            if tile_ids[i] >= 0:
                by_type.setdefault(tile_ids[i], []).append(i)

        # --- atomic triple collapse (normal types only) ---
        changed = True; new_active = active; atomic_picks = 0
        while changed:
            changed = False
            na = auto_clear(new_active)                  # settle specials between collapses
            if na != new_active:
                new_active = na
            pml = compute_pickable(new_active)
            bt = {}
            p = pml
            while p:
                low = p & -p; i = low.bit_length() - 1; p ^= low
                if tile_ids[i] >= 0:
                    bt.setdefault(tile_ids[i], []).append(i)
            cur_tsize = tray_size(tray)
            for tid, lst in bt.items():
                existing = tray_count(tray, tid); needed = 3 - existing
                if needed <= len(lst):
                    if cur_tsize + needed - 1 >= TRAY_SIZE:
                        continue
                    for i in lst[:needed]:
                        new_active ^= 1 << i
                    if existing > 0:
                        tray = tray - (existing << (tid * 2))
                    atomic_picks += needed; changed = True; break
        new_active = auto_clear(new_active)
        if new_active != active:
            if new_active == 0:
                stats["best_depth"] = max(stats["best_depth"], depth + atomic_picks)
                return True
            nk = (new_active, tray)
            if nk in dead:
                return False
            if dfs(new_active, tray, depth + atomic_picks):
                return True
            dead.add(nk); dead.add(key); return False

        # --- regular branching over normal pickable tiles ---
        picks = []
        for tid, lst in by_type.items():
            tc = tray_count(tray, tid)
            pr = 0 if tc == 2 else (1 if tc == 1 else 2)
            for i in lst:
                picks.append((pr, i))
        picks.sort()
        for _, i in picks:
            tid = tile_ids[i]; tc = tray_count(tray, tid)
            if tc == 2:
                new_tray = tray_sub3(tray_add(tray, tid), tid)
            else:
                if (tray_size(tray) + 1) >= TRAY_SIZE:
                    continue
                new_tray = tray_add(tray, tid)
            if dfs(active ^ (1 << i), new_tray, depth + 1):
                return True
        dead.add(key); return False

    try:
        result = dfs((1 << n) - 1, 0, 0)
    except _CapHit:
        return None, stats["best_depth"], stats["expansions"]
    except RecursionError:
        return None, stats["best_depth"], stats["expansions"]
    if verbose:
        print(f"*** {'SOLVED' if result else 'DEAD'} {stats['expansions']:,} exp depth={stats['best_depth']} "
              f"{time.time()-start:.1f}s | {len(dead):,} dead ***")
    return result, stats["best_depth"], stats["expansions"]


if __name__ == "__main__":
    # CLI: solve a level FILE the CORRECT way — builds the 2×2/3×3 footprint map from the JSON so
    # 3×3 specials aren't under-modelled as 2×2.  python solve_special.py <level.json> [max_exp]
    import json
    from tile_level_simulator import load_board_from_file
    if len(sys.argv) < 2:
        raise SystemExit("usage: python solve_special.py <level.json> [max_expansions]")
    p = os.path.abspath(sys.argv[1])
    cap = int(sys.argv[2]) if len(sys.argv) > 2 else 2_000_000
    data = json.load(open(p, encoding="utf-8"))
    board = load_board_from_file(p)
    if board is None:
        raise SystemExit(f"could not load board from {p}")
    halves = special_halves_from_level(data)
    st, depth, exp = solve_v3_special(board, special_ids=(1001, 1002), max_expansions=cap, special_halves=halves)
    n3 = sum(1 for h in halves.values() if h >= 1.5)
    print(f"{os.path.basename(p)}: solvable={st}  depth={depth}  exp={exp}  "
          f"| specials={len(halves)} ({n3}×3x3, {len(halves)-n3}×2x2)")
