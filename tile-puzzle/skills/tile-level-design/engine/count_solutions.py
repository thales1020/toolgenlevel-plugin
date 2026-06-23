"""Count winning paths for the saved candidate.

Uses memoized DP:  count_wins(state) = sum over pickable-actions a of count_wins(state + a)
Base: count_wins(active=0) = 1

This counts RAW distinct pick sequences that lead to win.
Enormous levels can have astronomical counts — we cap at MAX_COUNT.

Also reports:
- unique state count reachable from start
- number of states that lead to a win (winning states)
- states that are dead-ends (cannot reach win)
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tile_level_simulator import Board, Layer, Cell

TRAY_SIZE = 7
# No cap — Python ints handle arbitrary size


def build_bitmask_blocked_by(cells):
    n = len(cells)
    bb = [0] * n
    for i in range(n):
        ci = cells[i]
        for j in range(n):
            if i == j:
                continue
            cj = cells[j]
            if cj.layer_idx > ci.layer_idx:
                if abs(cj.x - ci.x) < 1.0 and abs(cj.y - ci.y) < 1.0:
                    bb[i] |= 1 << j
    return bb


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "fail80_candidate.json"
    data = json.load(open(path))
    b = Board(data["name"])
    for ld in data["layers"]:
        layer = Layer(ld["id"])
        for cd in ld["cells"]:
            c = Cell(cd["x"], cd["y"], ld["id"])
            c.tile_id = cd["tile_id"]
            layer.cells.append(c)
        b.layers.append(layer)
    print(f"Board: {b.name}, {b.total_cells()} cells, {len(b.layers)} layers")

    cells = b.all_cells()
    n = len(cells)
    tile_ids = [c.tile_id for c in cells]
    blocked_by = build_bitmask_blocked_by(cells)
    n_types = max(tile_ids) + 1

    def tray_count(tray, t): return (tray >> (t * 2)) & 3
    def tray_add(tray, t):   return tray + (1 << (t * 2))
    def tray_sub3(tray, t):  return tray - (3 << (t * 2))
    def tray_size(tray):
        s = 0
        for t in range(n_types):
            s += (tray >> (t * 2)) & 3
        return s

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

    # Memoize count_wins(state) -> int
    memo = {}
    stats = {"calls": 0, "memo_hits": 0}
    sys.setrecursionlimit(max(sys.getrecursionlimit(), n + 500))

    def count_wins(active, tray):
        stats["calls"] += 1
        if active == 0:
            return 1
        key = (active, tray)
        if key in memo:
            stats["memo_hits"] += 1
            return memo[key]

        pickable_mask = compute_pickable(active)
        if pickable_mask == 0:
            memo[key] = 0
            return 0

        total = 0
        p = pickable_mask
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                new_tray = tray_sub3(tray_add(tray, tid), tid)
            else:
                # Game over if tray would reach >= TRAY_SIZE without clear
                if (tray_size(tray) + 1) >= TRAY_SIZE:
                    continue
                new_tray = tray_add(tray, tid)
            new_active = active ^ low
            total += count_wins(new_active, new_tray)

        memo[key] = total
        return total

    t0 = time.time()
    initial_active = (1 << n) - 1
    total_paths = count_wins(initial_active, 0)
    elapsed = time.time() - t0

    # Post-analysis on memo
    win_states = sum(1 for v in memo.values() if v > 0)
    dead_states = sum(1 for v in memo.values() if v == 0)
    print(f"\nElapsed: {elapsed:.2f}s")
    print(f"Total DFS calls        : {stats['calls']:,}")
    print(f"Memo hits              : {stats['memo_hits']:,}")
    print(f"Unique states visited  : {len(memo):,}")
    print(f"  winning states       : {win_states:,}")
    print(f"  dead states          : {dead_states:,}")
    digits = len(str(total_paths))
    print(f"\nTotal raw winning paths: {total_paths:,}")
    print(f"  (= {total_paths:.3e}, {digits} digits)")


if __name__ == "__main__":
    main()
