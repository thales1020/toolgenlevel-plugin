"""Find and print the winning pick sequence for a saved candidate.

Uses DFS with atomic-triple optimization, but records the pick order.
Output: list of picks (step, x, y, layer, tile_id, tray_after).
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tile_level_simulator import Board, Layer, Cell

TRAY_SIZE = 7


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


def solve_with_path(board, max_expansions=None):
    cells = board.all_cells()
    n = len(cells)
    tile_ids = [c.tile_id for c in cells]
    blocked_by = build_bitmask_blocked_by(cells)
    n_types = max(tile_ids) + 1
    _cap = {"n": 0}
    _limit = max_expansions

    def tray_count(tray, t): return (tray >> (t * 2)) & 3
    def tray_add(tray, t):   return tray + (1 << (t * 2))
    def tray_sub3(tray, t):  return tray - (3 << (t * 2))
    def tray_size(tray):
        s = 0
        for t in range(n_types):
            s += (tray >> (t * 2)) & 3
        return s

    dead = set()
    sys.setrecursionlimit(max(sys.getrecursionlimit(), n + 200))

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

    class _CapHit(Exception):
        pass

    def dfs(active, tray, path):
        _cap["n"] += 1
        if _limit is not None and _cap["n"] >= _limit:
            raise _CapHit()
        if active == 0:
            return True
        key = (active, tray)
        if key in dead:
            return False

        # Atomic triple
        new_active = active
        new_tray = tray
        atomic_picks = []
        changed = True
        while changed:
            changed = False
            pm = compute_pickable(new_active)
            by_type = {}
            p = pm
            while p:
                low = p & -p
                i = low.bit_length() - 1
                p ^= low
                by_type.setdefault(tile_ids[i], []).append(i)
            cur_tsize = tray_size(new_tray)
            for tid, lst in by_type.items():
                existing = tray_count(new_tray, tid)
                needed = 3 - existing
                if needed <= len(lst):
                    if cur_tsize + needed - 1 >= TRAY_SIZE:
                        continue
                    for i in lst[:needed]:
                        new_active ^= 1 << i
                        atomic_picks.append(i)
                    if existing > 0:
                        new_tray = new_tray - (existing << (tid * 2))
                    changed = True
                    break

        if atomic_picks:
            saved_len = len(path)
            path.extend(atomic_picks)
            if new_active == 0:
                return True
            ak = (new_active, new_tray)
            if ak not in dead:
                if dfs(new_active, new_tray, path):
                    return True
                dead.add(ak)
            del path[saved_len:]
            dead.add(key)
            return False

        pickable_mask = compute_pickable(active)
        if pickable_mask == 0:
            dead.add(key)
            return False

        picks = []
        p = pickable_mask
        while p:
            low = p & -p
            i = low.bit_length() - 1
            p ^= low
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                priority = 0
            elif tc == 1:
                priority = 1
            else:
                priority = 2
            picks.append((priority, i))
        picks.sort()

        for _, i in picks:
            tid = tile_ids[i]
            tc = tray_count(tray, tid)
            if tc == 2:
                nt = tray_sub3(tray_add(tray, tid), tid)
            else:
                if (tray_size(tray) + 1) >= TRAY_SIZE:
                    continue
                nt = tray_add(tray, tid)
            na = active ^ (1 << i)
            path.append(i)
            if dfs(na, nt, path):
                return True
            path.pop()

        dead.add(key)
        return False

    path = []
    initial_active = (1 << n) - 1
    t0 = time.time()
    try:
        result = dfs(initial_active, 0, path)
    except _CapHit:
        result = None
    elapsed = time.time() - t0
    return result, path, elapsed, cells


def main():
    path_json = sys.argv[1] if len(sys.argv) > 1 else "fail80_candidate.json"
    data = json.load(open(path_json))
    b = Board(data["name"])
    for ld in data["layers"]:
        layer = Layer(ld["id"])
        for cd in ld["cells"]:
            c = Cell(cd["x"], cd["y"], ld["id"])
            c.tile_id = cd["tile_id"]
            layer.cells.append(c)
        b.layers.append(layer)

    print(f"Board: {b.name}, {b.total_cells()} cells, {len(b.layers)} layers")
    result, pick_indices, elapsed, cells = solve_with_path(b)
    print(f"Solve time: {elapsed:.2f}s, picks: {len(pick_indices)}\n")
    if not result:
        print("NO SOLUTION FOUND")
        return

    # Replay to show tray state at each step
    # NOTE: game displays tile labels as 1-indexed (internal id + 1)
    tray = {}
    print(f"{'Step':>4} {'Layer':>5} {'X':>6} {'Y':>6} {'Tile':>4}  Tray (display labels)")
    print("-" * 70)
    for step, idx in enumerate(pick_indices, 1):
        c = cells[idx]
        tid = c.tile_id
        disp = tid + 1  # game label
        tray[tid] = tray.get(tid, 0) + 1
        if tray[tid] >= 3:
            tray[tid] -= 3
            if tray[tid] == 0:
                del tray[tid]
        tray_str = ",".join(f"{t+1}x{n}" for t, n in sorted(tray.items())) or "(empty)"
        print(f"{step:>4} {c.layer_idx:>5} {c.x:>6.1f} {c.y:>6.1f} {disp:>4}  {tray_str}")


if __name__ == "__main__":
    main()
