"""Recursive DFS solver with atomic triples and transposition table.

Key optimizations vs beam BFS:
  1. Atomic triple collapse: if 3+ same-type tiles are pickable at once,
     pick all 3 in one step (depth -= 2 per triple). Often triples compound:
     clearing 3 top-layer tiles of type X immediately makes a lower row
     pickable where another 3 of some type Y may now be pickable.
  2. DFS recursion: memory O(depth) not O(frontier). Depth <= 78.
  3. Transposition table: dict mapping canonical state -> dead/alive bool.
     Dead states are memoized so we never re-explore.
  4. Early termination: first solution short-circuits.

Returns (status, best_depth, expansions).
  status: True=solvable, False=exhaustively dead, None=expansion cap hit.
"""
import sys, time


TRAY_SIZE = 7


def build_bitmask_visibility(cells):
    n = len(cells)
    blocked_by = [0] * n
    blocks = [0] * n
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j:
                continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx:
                if abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                    blocked_by[i] |= 1 << j
                    blocks[j] |= 1 << i
    return blocked_by, blocks


def solve_v3(board, max_expansions=None, verbose=False):
    cells = board.all_cells()
    n = len(cells)
    tile_ids = [c.tile_id for c in cells]
    blocked_by, blocks = build_bitmask_visibility(cells)
    n_types = max(tile_ids) + 1

    # Tray packed in int: 2 bits per type (counts 0-3)
    def tray_count(tray, t): return (tray >> (t * 2)) & 3
    def tray_add(tray, t):   return tray + (1 << (t * 2))
    def tray_sub3(tray, t):  return tray - (3 << (t * 2))
    def tray_size(tray):
        s = 0
        for t in range(n_types):
            s += (tray >> (t * 2)) & 3
        return s

    # Transposition table: (active_mask, tray_int) -> 0 (dead) or 1 (alive)
    # We only store DEAD states (alive = short-circuit return True)
    dead = set()

    stats = {"expansions": 0, "best_depth": 0}
    start = time.time()
    cap = max_expansions

    sys.setrecursionlimit(max(sys.getrecursionlimit(), n + 100))

    def compute_pickable(active):
        p = 0
        a = active
        while a:
            low = a & -a
            i = low.bit_length() - 1
            if not (blocked_by[i] & active):
                p |= low
            a ^= low
        return p

    def dfs(active, tray, depth):
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
            dead.add(key)
            return False

        # Group pickable by tile_id
        by_type = {}  # tile_id -> list of bit positions
        p = pickable_mask
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            by_type.setdefault(tile_ids[i], []).append(i)

        # --- Optimization 1: atomic triple (3+ same-type pickable) ---
        # If ANY type has 3+ pickable tiles AND tray_count(that type) == 0,
        # picking 3 of them forms an instant triple with no tray residue.
        # This is always a "free move" -- player would always take it.
        # Do them eagerly, as many as available. Track total picks for depth accounting.
        changed = True
        new_active = active
        atomic_picks = 0
        while changed:
            changed = False
            pickable_mask_local = compute_pickable(new_active)
            by_type_local = {}
            p = pickable_mask_local
            while p:
                low = p & -p
                i = low.bit_length() - 1
                p ^= low
                by_type_local.setdefault(tile_ids[i], []).append(i)
            cur_tsize = tray_size(tray)
            for tid, lst in by_type_local.items():
                existing = tray_count(tray, tid)
                needed = 3 - existing
                if needed <= len(lst):
                    # Intermediate tray size during atomic: peaks at cur_tsize + (needed-1)
                    # (after needed-1 picks, before the completing pick clears).
                    # Must stay < TRAY_SIZE (game over rule).
                    if cur_tsize + needed - 1 >= TRAY_SIZE:
                        continue  # atomic unsafe, try another type
                    for i in lst[:needed]:
                        new_active ^= 1 << i
                    if existing > 0:
                        tray = tray - (existing << (tid * 2))
                    atomic_picks += needed
                    changed = True
                    break
        if new_active != active:
            if new_active == 0:
                if depth + atomic_picks > stats["best_depth"]:
                    stats["best_depth"] = depth + atomic_picks
                return True
            new_key = (new_active, tray)
            if new_key in dead:
                return False
            if dfs(new_active, tray, depth + atomic_picks):
                return True
            dead.add(new_key)
            dead.add(key)
            return False

        # --- Optimization 2: action symmetry ---
        # Within same type, pickable tiles that share the SAME blocks_mask
        # collapse to a single canonical action. (Picking either leads to
        # isomorphic futures via the transposition table since resulting
        # active_mask bits flip in equivalent positions.)
        # But since active_mask differs, it won't dedupe via TT alone.
        # We apply the weaker rule: only expand distinct bit positions.
        # (Still safe; dedup happens via visited.)

        # --- Regular branching: try each pickable ---
        # Order: prefer picks that complete a pair (tray has 2 of this type)
        #        since those immediately clear (no tray overflow risk)
        picks_with_priority = []
        for tid, lst in by_type.items():
            tc = tray_count(tray, tid)
            for i in lst:
                if tc == 2:
                    priority = 0  # completes triple
                elif tc == 1:
                    priority = 1  # pair progress
                else:
                    priority = 2
                picks_with_priority.append((priority, i))
        picks_with_priority.sort()

        for _, i in picks_with_priority:
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                new_tray = tray_sub3(tray_add(tray, tid), tid)
            else:
                # game over if tray reaches TRAY_SIZE without a triple clear
                if (tray_size(tray) + 1) >= TRAY_SIZE:
                    continue
                new_tray = tray_add(tray, tid)

            new_act = active ^ (1 << i)
            if dfs(new_act, new_tray, depth + 1):
                return True

        dead.add(key)
        return False

    class _CapHit(Exception):
        pass

    try:
        initial_active = (1 << n) - 1
        result = dfs(initial_active, 0, 0)
    except _CapHit:
        elapsed = time.time() - start
        if verbose:
            print(f"*** CAP HIT {stats['expansions']:,} at depth {stats['best_depth']}, {elapsed:.1f}s ***")
        return None, stats["best_depth"], stats["expansions"]
    except RecursionError:
        elapsed = time.time() - start
        if verbose:
            print(f"*** RECURSION LIMIT at depth {stats['best_depth']}, {elapsed:.1f}s ***")
        return None, stats["best_depth"], stats["expansions"]

    elapsed = time.time() - start
    if verbose:
        verdict = "SOLVED" if result else "DEAD"
        print(f"*** {verdict} after {stats['expansions']:,} exp, depth={stats['best_depth']}, {elapsed:.1f}s ***")
        print(f"    transposition table: {len(dead):,} dead states memoized")
    return (result, stats["best_depth"], stats["expansions"])


# Compatibility shim
def solve(board, beam_width=None, log_every=None, max_expansions=None, verbose=True):
    return solve_v3(board, max_expansions=max_expansions, verbose=verbose)


if __name__ == "__main__":
    import os, json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from tile_level_simulator import Board, Layer, Cell, TEEngine, load_board_from_file

    # Benchmark on 3 cases
    def bench(name, config_fn):
        b = load_board_from_file(os.path.abspath("sample_levels/NewLayout_L50.json"))
        config_fn(b)
        print(f"\n=== {name} ===")
        print(f"Board: {b.total_cells()} cells")
        t0 = time.time()
        res, d, e = solve_v3(b, max_expansions=2_000_000, verbose=True)
        print(f"Result: {res}, depth={d}, exp={e:,}, time={time.time()-t0:.2f}s")

    def cfg_solvable(b):
        eng = TEEngine(); eng.validate = True; eng.color_count = 4
        eng.generate(b)

    def cfg_hard(b):
        eng = TEEngine(); eng.validate = False
        eng.color_count = 12; eng.hard_code = 0; eng.distance = 15
        eng.less_type = True; eng.top3_easy = True
        eng.val_replace = True; eng.val_mode = 2
        eng.generate(b)

    bench("SOLVABLE easy (4 colors)", cfg_solvable)
    bench("HARD 12 types", cfg_hard)
