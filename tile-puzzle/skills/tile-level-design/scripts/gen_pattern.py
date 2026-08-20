"""gen_pattern.py — ONE parameterized generator for the 6 design patterns (SKILL.md §4), on ANY layout.

Replaces the per-layout one-off research templates (find_trap_fast / find_easy_* / find_bridge_L21 /
find_clear50_trap / find_guided_trap_L21) which were pinned to L20/L21/L50. Every hardcoded geometry
constant here is derived from the given layout instead.

Patterns (--pattern):
  1 trap     — TEEngine search, high player FAIL rate (--metric greedy|random)
  2 easytop  — TEEngine search, STRUCTURAL top-layers-easy (triple_frac in the top half)
  3 bridge   — CUSTOM: easy-top + recurring "bridge" types spanning depth + trap-bottom
  4 clear50  — CUSTOM auto-strategy: greedy clears ~X% then traps (the generic reference)
  5 guided   — CUSTOM 3-band gradient with trap breadcrumbs
  6 score    — TEEngine search, score band only (WARN: trivially easy without --score-min)

Greedy is an EVALUATOR (a simulated greedy player measuring fail%/cleared) used only in the FILTER
stage — never a level generator. Levels are made by TEEngine (patterns 1/2/6) or custom hand-assignment
(3/4/5); greedy/random playout then gates the pattern's difficulty property.

Score bands are OFF by default (they were tuned per-layout and reject ~everything elsewhere) — pass
--score-min/--score-max to enable. Attempts are a REJECTION SAMPLER: default 2000, raise for hard bands.

Usage:
  python gen_pattern.py --pattern N --layout <name|path> [--out o.json]
     [--attempts 2000] [--color-count C] [--score-min S --score-max S]
     [--metric greedy|random] [--fail-rate 0.9]
     [--clear-min 0.40 --clear-max 0.60] [--triple-frac 0.85]
     [--bridge-types B] [--variant easy|harder|hard] [--seed 1]
Output = game stones format ({group,tiles,layers:[{index,stones:[{i,x,y}]}],stacks,metadata}); run
export_game_format.py after if you need it stripped to the raw game file.
"""
import sys, os, json, argparse, random, time
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows cp1252 console safety
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.join(os.path.dirname(HERE), "engine")
sys.path.insert(0, ENGINE)
sys.path.insert(0, HERE)
from tile_level_simulator import (Board, Layer, Cell, TEEngine, DifficultyScorer,
                                  load_board_from_file, load_scoring_weights)
from verify_smart_v3 import solve_v3

TRAY = 7
SOLVE_CAP = 100_000          # solvable boards find a win in ~25k expansions; unsolvable exhaust the cap,
                             # so keep this modest so rejection of unsolvable candidates stays fast.
# The 30 REAL Group_1 art ids that ship with the game (verified against reference levels). Generated levels
# emit sequential type ids by default; --art-ids remaps onto these so they render with real sprites.
VALID_GROUP1_IDS = [85] + list(range(142, 171))
_SAMPLES = os.path.join(os.path.dirname(HERE), "sample_layouts")
WEIGHTS = load_scoring_weights()


# ───────────────────────── shared: layout, bitmask, ÷3 trim ─────────────────────────

def _resolve_layout(name_or_path):
    """Accept a bare id ('L20'), a filename ('NewLayout_L20.json'), or an absolute path."""
    if os.path.isfile(name_or_path):
        return os.path.abspath(name_or_path)
    for cand in (name_or_path, f"NewLayout_{name_or_path}.json",
                 name_or_path if name_or_path.endswith(".json") else name_or_path + ".json"):
        p = os.path.join(_SAMPLES, cand)
        if os.path.isfile(p):
            return os.path.abspath(p)
    raise SystemExit(f"layout not found: {name_or_path} (looked in {_SAMPLES})")


def _covered(c, cells):
    return any(o.layer_idx > c.layer_idx and abs(o.x - c.x) < 1 and abs(o.y - c.y) < 1 for o in cells)


def _load_trimmed(path, allow_trim=False):
    """Load the layout for tile assignment. If total_cells isn't ÷3, this WOULD require dropping cells
    to partition cleanly -- that silently turns the named layout into a different one (Layout_A ->
    Layout_A1) unless the caller explicitly opts in. Default: hard-fail (matches find_hybrid_fast.py's
    existing behavior for the same precondition -- consistency, and this project's "never silently ship
    degraded/altered input" rule, SKILL.md sec.15). Pass allow_trim=True (CLI: --allow-trim) to accept
    dropping cells; the trim is then recorded in the caller's output metadata, never silent.
    Returns (positions=[(x,y,layer)], n_layers, trim_info) where trim_info is None or
    {"dropped_cells": N} when a trim actually happened."""
    board = load_board_from_file(path)
    if board is None:
        raise SystemExit(f"could not load board from {path} (absolute path required on Windows)")
    cells = board.all_cells()
    specials = [c for c in cells if c.tile_id >= 1000]
    if specials:
        raise SystemExit(
            f"layout {path} already has {len(specials)} special cell(s) (bonus/mission, tile_id>=1000). "
            f"gen_pattern.py assigns fresh tile ids to EVERY cell it loads -- pointing it at an "
            f"already-special level would silently overwrite the special(s) into normal tiles, losing "
            f"the mission/bonus and corrupting the ÷3 count and solvability check. gen_pattern.py is for "
            f"a geometry-only layout (no tiles). To rebuild a level that needs specials: gen the NORMAL "
            f"level first (on the bare layout), then add specials back with reserve_special.py / "
            f"add_special_cells.py as a separate POST step -- never re-tile a file that already has them.")
    rem = len(cells) % 3
    trim_info = None
    if rem:
        if not allow_trim:
            raise SystemExit(
                f"layout {path} has {len(cells)} cells, not divisible by 3 ({rem} extra) -- "
                f"assigning tiles would require dropping {rem} cell(s), silently altering this "
                f"layout's geometry. Fix the layout upstream (gen-layout), or pass --allow-trim "
                f"to explicitly accept dropping {rem} cell(s) (recorded in output metadata).")
        ex = [c for c in cells if not _covered(c, cells)]
        random.shuffle(ex)
        drop = {id(c) for c in ex[:rem]}
        cells = [c for c in cells if id(c) not in drop]
        trim_info = {"dropped_cells": rem}
    positions = [(c.x, c.y, c.layer_idx) for c in cells]
    n_layers = len({li for _, _, li in positions})
    return positions, n_layers, trim_info


def _build_bb(positions):
    """Blocking bitmask + blocker count (the universal rule: j blocks i iff j is higher and overlaps)."""
    n = len(positions)
    bb = [0] * n
    bc = [0] * n
    for i in range(n):
        xi, yi, li = positions[i]
        for j in range(n):
            if i == j:
                continue
            xj, yj, lj = positions[j]
            if lj > li and abs(xj - xi) < 1.0 and abs(yj - yi) < 1.0:
                bb[i] |= 1 << j
                bc[i] += 1
    return bb, bc


# ───────────────────────── shared: the ONE playout metric ─────────────────────────

def playout(tile_ids, bb, n, mode="greedy", runs=300):
    """Simulated player over `runs` games. mode 'greedy' = prefer completing a triple>pair>random (10%
    pure-random noise); mode 'random' = always uniform-random pick. Fail = tray reaches 7 with no triple.
    Returns (fail_rate, avg_cleared). This is the consolidation of the 6 duplicated template copies."""
    fails = 0
    total_cleared = 0
    for _ in range(runs):
        active = (1 << n) - 1
        tray = {}
        cleared = 0
        while active:
            pickable = []
            a = active
            while a:
                low = a & -a
                ii = low.bit_length() - 1
                a ^= low
                if not (bb[ii] & active):
                    pickable.append(ii)
            if not pickable:
                fails += 1
                break
            if mode == "random" or random.random() < 0.1:
                ii = random.choice(pickable)
            else:
                triple = [k for k in pickable if tray.get(tile_ids[k], 0) == 2]
                if triple:
                    ii = random.choice(triple)
                else:
                    pair = [k for k in pickable if tray.get(tile_ids[k], 0) == 1]
                    ii = random.choice(pair) if pair else random.choice(pickable)
            tid = tile_ids[ii]
            active ^= 1 << ii
            cleared += 1
            tray[tid] = tray.get(tid, 0) + 1
            if tray[tid] >= 3:
                tray[tid] -= 3
                if tray[tid] == 0:
                    del tray[tid]
            if sum(tray.values()) >= TRAY and not any(v >= 3 for v in tray.values()):
                fails += 1
                break
        total_cleared += cleared
    return fails / runs, total_cleared / runs


# ───────────────────────── shared: board build + scoring + solve ─────────────────────────

def _clone_board(positions, tile_ids):
    """Engine Board from (positions, tile_ids) — for scoring + solving."""
    by = {}
    for i, (x, y, li) in enumerate(positions):
        by.setdefault(li, []).append((x, y, tile_ids[i]))
    b = Board("pattern")
    for li in sorted(by):
        ly = Layer(li)
        for (x, y, t) in by[li]:
            c = Cell(x, y, li)
            c.tile_id = t
            ly.cells.append(c)
        b.layers.append(ly)
    return b


def _score(board):
    return DifficultyScorer.compute_full_score(board, weights=WEIGHTS)["final_score"]


def _solvable(board, cap):
    return solve_v3(board, max_expansions=cap, verbose=False)[0] is True


def _id_map(tile_ids, raw_ids):
    """Map each distinct 0-based type to the emitted `i`. Default: remap onto REAL Group_1 art ids
    (85,142-170) — a bijective per-level relabel with NO effect on difficulty/solvability (same type
    partition) so the level ships with real sprites. Falls back to raw `tid+1` when raw_ids is set or a
    level has more types than the 30-id art pool."""
    distinct = sorted(set(tile_ids))
    if not raw_ids and len(distinct) <= len(VALID_GROUP1_IDS):
        return {t: VALID_GROUP1_IDS[k] for k, t in enumerate(distinct)}, True
    return {t: t + 1 for t in distinct}, False


def _to_game_json(positions, tile_ids, meta, id_map):
    by = {}
    for i, (x, y, li) in enumerate(positions):
        by.setdefault(li, []).append({"i": id_map[tile_ids[i]], "x": x, "y": y})
    layers = [{"index": li, "stones": by[li]} for li in sorted(by)]
    return {"group": 1, "tiles": "", "layers": layers, "stacks": [], "metadata": meta}


# ───────────────────────── shared: TEEngine generation (patterns 1/2/6) ─────────────────────────

def _teengine_tile_ids(positions, n_layers, cc, distance, hard_code, knobs, board_for_flags):
    """Run the engine's bind sequence on a fresh board and return tile_ids (mirrors the proven
    reserve_special path, but honouring the *_easy / less_type / distance knobs)."""
    b = Board("gen")
    by = {}
    for (x, y, li) in positions:
        by.setdefault(li, []).append((x, y))
    for li in sorted(by):
        ly = Layer(li)
        for (x, y) in by[li]:
            c = Cell(x, y, li)
            c.tile_id = -1
            ly.cells.append(c)
        b.layers.append(ly)
    eng = TEEngine()
    eng.validate = False
    eng.color_count = cc
    eng.hard_code = hard_code
    eng.distance = distance
    eng.level_number = 200                       # >100 so the distance knob is active; >=51 for val_replace
    for k, v in knobs.items():
        setattr(eng, k, v)
    if cc > 6:
        eng.style_mode = 3; eng.extended = True
    elif cc > 5:
        eng.style_mode = 7
    cells = b.all_cells()
    eff = eng._get_effective_cc()
    pool = eng._build_icon_pool(len(cells), eff)
    flags = eng._compute_knob_flags(b, eff)
    eng._bind_random(cells, pool, eff, flags)
    eng._fix_x3_distribution(cells, eff)
    # extract tile_ids in the SAME order as `positions`
    pos_index = {(round(x, 4), round(y, 4), li): idx for idx, (x, y, li) in enumerate(positions)}
    tile_ids = [0] * len(positions)
    for c in cells:
        key = (round(c.x, 4), round(c.y, 4), c.layer_idx)
        if key in pos_index:
            tile_ids[pos_index[key]] = c.tile_id
    return tile_ids


# ───────────────────────── shared: layer bands + custom-config solver ─────────────────────────

def _top_half(positions):
    """Indices split into (top_half, bottom_half): accumulate layers from the highest index until the
    cumulative cell count reaches n//2. Generalises the templates' literal 'top 3 layers'."""
    n = len(positions)
    per_layer = {}
    for i, (_, _, li) in enumerate(positions):
        per_layer.setdefault(li, []).append(i)
    top_ids, cum = set(), 0
    for li in sorted(per_layer, reverse=True):
        top_ids.add(li)
        cum += len(per_layer[li])
        if cum >= n // 2:
            break
    top = [i for i in range(n) if positions[i][2] in top_ids]
    bot = [i for i in range(n) if positions[i][2] not in top_ids]
    return top, bot, top_ids


def _bands(positions, k=3):
    """Split the distinct layers into k contiguous bands (band 0 = TOP). Returns list of index-lists."""
    layers = sorted({li for _, _, li in positions}, reverse=True)   # top first
    if not layers:
        return [[] for _ in range(k)]
    chunk = max(1, (len(layers) + k - 1) // k)
    band_of = {}
    for pos, li in enumerate(layers):
        band_of[li] = min(k - 1, pos // chunk)
    out = [[] for _ in range(k)]
    for i, (_, _, li) in enumerate(positions):
        out[band_of[li]].append(i)
    return out


def _configs_6a3b(n, ne_min=3, ne_max=10, nt_min=3):
    """Every (n_easy, n_trap) with n_easy*6 + n_trap*3 == n (each group divisible cleanly). Since
    6a+3b=3(2a+b), this is satisfiable for any ÷3 board with enough cells."""
    out = []
    for ne in range(ne_min, ne_max):
        rem = n - ne * 6
        if rem > 0 and rem % 3 == 0 and rem // 3 >= nt_min:
            out.append((ne, rem // 3))
    return out


# ═══════════════════════════════ PATTERNS ═══════════════════════════════

def pat_teengine(ctx, a, structural=None, want_fail=None, metric="greedy", label="trap"):
    """Shared TEEngine search loop for patterns 1 (fail), 2 (structural), 6 (score-only).
    structural(tile_ids)->bool gates P2; want_fail gates P1; neither gates P6."""
    positions, bb, bc, n, n_layers = ctx["positions"], ctx["bb"], ctx["bc"], ctx["n"], ctx["n_layers"]
    cc_lo = max(5, (a.color_count or 12) - 3)
    cc_hi = (a.color_count or 18) + 3
    KNOBS = [dict(), dict(top3_easy=True), dict(less_type=True),
             dict(top3_easy=True, less_type=True), dict(up_easy=True)]
    t0 = time.time()
    checked = 0
    for attempt in range(a.attempts):
        cc = a.color_count or random.randint(cc_lo, cc_hi)
        hard = random.choice([0, 1, 2, 3])
        knobs = dict(random.choice(KNOBS))                  # COPY — never mutate the shared list entry
        dist = random.choice([0, 0, 3, 5, 8])               # fresh each attempt (not frozen at build time)
        tile_ids = _teengine_tile_ids(positions, n_layers, cc, dist, hard, knobs, None)
        nt = len(set(tile_ids))
        if nt < 3:                                          # (--color-count only SEEDS cc; ÷3 repair may shift nt)
            continue
        # CHEAP discriminators FIRST (tile_ids / greedy ≈ 0.1s) — reject BEFORE the ~1.5s solve_v3.
        if structural is not None and not structural(tile_ids):
            continue                                        # P2: top-half easy (tile_ids only)
        if want_fail is not None:                           # P1: fail-rate IS the target -> gate before solve
            fq, _ = playout(tile_ids, bb, n, metric, 30)
            if fq < 0.5:
                continue
            fr, ac = playout(tile_ids, bb, n, metric, 300)
            if fr < want_fail:
                continue
        else:
            fr = ac = None
        board = _clone_board(positions, tile_ids)
        if a.score_min is not None or a.score_max is not None:
            s = _score(board)
            if a.score_min is not None and s < a.score_min:
                continue
            if a.score_max is not None and s > a.score_max:
                continue
        else:
            s = None
        if not _solvable(board, SOLVE_CAP):                 # EXPENSIVE — runs only on survivors
            continue
        checked += 1
        info = {"pattern": label, "n_types": nt, "score": (round(s, 1) if s is not None else None),
                "fail_rate": (round(fr, 2) if fr is not None else None),
                "avg_cleared": (round(ac, 1) if ac is not None else None),
                "attempt": attempt, "seconds": round(time.time() - t0, 1)}
        return tile_ids, info
        # (loop continues otherwise)
    return None


def pat_custom_clear(ctx, a):
    """Pattern 4 (clear50): greedy clears a TARGET fraction then hits a wall. Generalised beyond the L20
    template: easy types (×6) go on the N most-ACCESSIBLE cells (lowest blocker-count = cleared earliest),
    traps (×3) on the deeper cells. Sizing the easy zone to the clear target (≈clear_mid·n cells) works on
    ANY geometry — including top-heavy layouts where a 'fill the top half' rule over-fills and dead-ends."""
    positions, bb, bc, n, n_layers = ctx["positions"], ctx["bb"], ctx["bc"], ctx["n"], ctx["n_layers"]
    tier1 = [i for i in range(n) if bc[i] == 0]
    top, bot, _ = _top_half(positions)                      # easy zone = top half (faithful clear50 port)
    top = sorted(top, key=lambda i: bc[i])
    configs = [c for c in _configs_6a3b(n) if c[0] * 6 >= len(top)]  # NE must fill the top half
    if not configs:
        configs = _configs_6a3b(n)
    if not configs:
        raise SystemExit(f"no 6a+3b config for {n} cells")
    cmin = int((a.clear_min if a.clear_min is not None else 0.40) * n)
    cmax = int((a.clear_max if a.clear_max is not None else 0.60) * n)
    fail_min = a.fail_rate if a.fail_rate is not None else 0.80
    best = None
    best_attempt = 0                                         # closest-to-band fallback (best-effort)
    t0 = time.time()
    for attempt in range(a.attempts):
        NE, NT = random.choice(configs)
        easy = list(range(NE))
        trap = list(range(NE, NE + NT))
        assigned = {}
        pool = []
        for t in easy:
            pool.extend([t] * 6)
        random.shuffle(pool)
        if len(pool) < len(top):
            continue
        for i, idx in enumerate(top):
            assigned[idx] = pool[i]
        trap_pool = []
        for t in trap:
            trap_pool.extend([t] * 3)
        counts = {}
        for v in assigned.values():
            counts[v] = counts.get(v, 0) + 1
        for t in easy:
            trap_pool.extend([t] * (6 - counts.get(t, 0)))
        random.shuffle(trap_pool)
        una = [i for i in range(n) if i not in assigned]
        if len(trap_pool) != len(una):
            continue
        for i, idx in enumerate(una):
            assigned[idx] = trap_pool[i]
        tile_ids = [assigned.get(i, 0) for i in range(n)]
        if len(set(tile_ids)) < NE + NT - 2:
            continue
        pt = {}
        for i in tier1:
            pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
        if tier1 and sum(1 for v in pt.values() if v >= 2) < 1:
            continue
        board = _clone_board(positions, tile_ids)
        if not _solvable(board, 100_000):            # cheap reject of unsolvable BEFORE the 300-playout
            continue
        if a.score_min is not None and _score(board) < a.score_min:
            continue
        if a.score_max is not None and _score(board) > a.score_max:
            continue
        fr, ac = playout(tile_ids, bb, n, "greedy", 300)
        in_band = bool(cmin <= ac <= cmax)
        info = {"pattern": "clear50", "n_types": len(set(tile_ids)), "fail_rate": round(fr, 2),
                "avg_cleared": round(ac, 1), "cleared_pct": round(ac / n * 100), "in_band": in_band,
                "easy": NE, "trap": NT, "attempt": attempt, "seconds": round(time.time() - t0, 1)}
        if in_band and fr >= fail_min:
            return tile_ids, info                            # ideal: in the clear band with the fail floor
        # else track the best SOLVABLE candidate: prefer in-band, then meeting the fail floor, then closeness
        key = (0 if in_band else 1, 0 if fr >= fail_min else 1, min(abs(ac - cmin), abs(ac - cmax)))
        if best is None or key < best[0]:
            best = (key, tile_ids, info); best_attempt = attempt
        if best is not None and attempt - best_attempt >= 60:  # stall: no improvement in 60 tries (honours --attempts)
            break
    if best is not None:
        best[2]["note"] = (f"best-effort (target clear [{cmin},{cmax}] fail>={fail_min} not fully met on "
                           f"this geometry): cleared {best[2]['avg_cleared']} fail {best[2]['fail_rate']}")
        return best[1], best[2]
    return None


def pat_bridge(ctx, a):
    """Pattern 3 (bridge): easy-only (top), BRIDGE types ×6 spanning top→bottom (familiar recurring
    tiles), trap-only ×3 (bottom). Group counts re-solved for the layout's cell count."""
    positions, bb, bc, n, n_layers = ctx["positions"], ctx["bb"], ctx["bc"], ctx["n"], ctx["n_layers"]
    tier1 = [i for i in range(n) if bc[i] == 0]
    per_layer = {}
    for i, (_, _, li) in enumerate(positions):
        per_layer.setdefault(li, []).append(i)
    layer_ids = sorted(per_layer, reverse=True)                       # top first
    B = a.bridge_types or {"easy": 4, "harder": 4, "hard": 2}.get(a.variant, 3)
    # solve 3*ne + 6*B + 3*nt == n  ->  ne + nt = (n - 6B)/3 ; split ~half/half
    rem = n - 6 * B
    if rem <= 0 or rem % 3 != 0:
        # nudge B down until feasible
        while B > 1 and (rem <= 0 or rem % 3 != 0):
            B -= 1
            rem = n - 6 * B
    if rem <= 0 or rem % 3 != 0:
        raise SystemExit(f"no bridge config for {n} cells (try --bridge-types)")
    groups = rem // 3
    ne = groups // 2
    nt = groups - ne
    t0 = time.time()
    for attempt in range(a.attempts):
        easy = list(range(ne))
        bridge = list(range(ne, ne + B))
        trap = list(range(ne + B, ne + B + nt))
        pools = {li: per_layer[li][:] for li in layer_ids}
        for li in pools:
            random.shuffle(pools[li])
        assigned = {}

        def draw(pref, k):
            got = []
            for li in list(pref) + layer_ids:
                while pools.get(li) and len(got) < k:
                    got.append(pools[li].pop())
                if len(got) >= k:
                    break
            return got

        ok = True
        # easy-only ×3 → top 2 layers
        for t in easy:
            cells = draw(layer_ids[:2], 3)
            if len(cells) < 3:
                ok = False; break
            for c in cells:
                assigned[c] = t
        # bridge ×6 → 1 per layer descending (span)
        if ok:
            for t in bridge:
                placed = 0
                for li in layer_ids:
                    if pools.get(li):
                        assigned[pools[li].pop()] = t
                        placed += 1
                    if placed >= 6:
                        break
                # top up if fewer than 6 layers
                while placed < 6:
                    extra = draw(layer_ids, 1)
                    if not extra:
                        ok = False; break
                    assigned[extra[0]] = t
                    placed += 1
                if not ok:
                    break
        # trap-only ×3 → bottom 2 layers
        if ok:
            for t in trap:
                cells = draw(layer_ids[-2:], 3)
                if len(cells) < 3:
                    ok = False; break
                for c in cells:
                    assigned[c] = t
        if not ok or len(assigned) != n:
            continue
        tile_ids = [assigned[i] for i in range(n)]
        pt = {}
        for i in tier1:
            pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
        if sum(1 for v in pt.values() if v >= 2) < 2:                 # bridge gate: instant>=2
            continue
        board = _clone_board(positions, tile_ids)
        if not _solvable(board, 100_000):
            continue
        if a.score_min is not None and _score(board) < a.score_min:
            continue
        if a.score_max is not None and _score(board) > a.score_max:
            continue
        fr, ac = playout(tile_ids, bb, n, "greedy", 300)
        info = {"pattern": "bridge", "variant": a.variant, "n_types": len(set(tile_ids)),
                "easy": ne, "bridge": B, "trap": nt, "fail_rate": round(fr, 2),
                "avg_cleared": round(ac, 1), "attempt": attempt, "seconds": round(time.time() - t0, 1)}
        return tile_ids, info
    return None


def pat_guided(ctx, a):
    """Pattern 5 (guided): a STEEP gradient — easy types concentrated in the TOP BAND only (a strong
    guided start / instant triples), then the remaining easy + ALL traps distributed over the lower two
    bands using the clear50-proven coherent-triple fill (each trap type stays a whole ×3 set, so it is
    completable → solvable). Distinct from clear50, which spreads easy over the whole top HALF; guided's
    easy zone is just the top third, giving a sharper easy→hard descent. Bands from n_layers."""
    positions, bb, bc, n, n_layers = ctx["positions"], ctx["bb"], ctx["bc"], ctx["n"], ctx["n_layers"]
    tier1 = [i for i in range(n) if bc[i] == 0]
    band0, band1, band2 = _bands(positions, 3)
    lower = band1 + band2
    configs = _configs_6a3b(n)
    if not configs:
        raise SystemExit(f"no 6a+3b config for {n} cells")
    cmin = int((a.clear_min if a.clear_min is not None else 0.20) * n)   # guided traps sooner than clear50
    cmax = int((a.clear_max if a.clear_max is not None else 0.50) * n)
    fail_min = a.fail_rate if a.fail_rate is not None else 0.80
    best = None
    best_attempt = 0
    t0 = time.time()
    for attempt in range(a.attempts):
        NE, NT = random.choice(configs)
        easy = list(range(NE))
        trap = list(range(NE, NE + NT))
        assigned = {}
        # TOP band: fill with easy types (front types concentrated for instant triples), each easy <=6
        pool0 = []
        for t in easy:
            pool0.extend([t] * 6)
        random.shuffle(pool0)
        if len(pool0) < len(band0):
            continue
        for k, idx in enumerate(band0):
            assigned[idx] = pool0[k]
        used = {}
        for v in assigned.values():
            used[v] = used.get(v, 0) + 1
        # LOWER bands: leftover easy copies + all trap ×3 (coherent triples) shuffled together
        rest = []
        for t in easy:
            rest.extend([t] * (6 - used.get(t, 0)))
        for t in trap:
            rest.extend([t] * 3)
        random.shuffle(rest)
        una = [i for i in range(n) if i not in assigned]
        if len(rest) != len(una):
            continue
        for k, idx in enumerate(una):
            assigned[idx] = rest[k]
        tile_ids = [assigned[i] for i in range(n)]
        pt = {}
        for i in tier1:
            pt[tile_ids[i]] = pt.get(tile_ids[i], 0) + 1
        if sum(1 for v in pt.values() if v >= 2) < 2:
            continue
        board = _clone_board(positions, tile_ids)
        if not _solvable(board, 100_000):            # cheap reject BEFORE the 300-playout
            continue
        if a.score_min is not None and _score(board) < a.score_min:
            continue
        if a.score_max is not None and _score(board) > a.score_max:
            continue
        fr, ac = playout(tile_ids, bb, n, "greedy", 300)
        in_band = bool(cmin <= ac <= cmax)
        info = {"pattern": "guided", "n_types": len(set(tile_ids)), "easy": NE, "trap": NT,
                "fail_rate": round(fr, 2), "avg_cleared": round(ac, 1), "in_band": in_band,
                "cleared_pct": round(ac / n * 100), "attempt": attempt, "seconds": round(time.time() - t0, 1)}
        if in_band and fr >= fail_min:
            return tile_ids, info
        key = (0 if in_band else 1, 0 if fr >= fail_min else 1, min(abs(ac - cmin), abs(ac - cmax)))
        if best is None or key < best[0]:
            best = (key, tile_ids, info); best_attempt = attempt
        if best is not None and attempt - best_attempt >= 60:
            break
    if best is not None:
        best[2]["note"] = (f"best-effort (target clear [{cmin},{cmax}] fail>={fail_min} not fully met on "
                           f"this geometry): cleared {best[2]['avg_cleared']} fail {best[2]['fail_rate']}")
        return best[1], best[2]
    return None


# ───────────────────────── structural gate for pattern 2 ─────────────────────────

def _make_structural(ctx, triple_frac_min):
    positions, n = ctx["positions"], ctx["n"]
    top, bot, _ = _top_half(positions)
    top_set = set(top)

    def gate(tile_ids):
        counts = {}
        for i in top:
            counts[tile_ids[i]] = counts.get(tile_ids[i], 0) + 1
        easy_cells = sum(v for v in counts.values() if v >= 3)
        return len(top) > 0 and (easy_cells / len(top)) >= triple_frac_min
    return gate


# ───────────────────────── dispatch + parallel worker ─────────────────────────

def run_pattern(ctx, a):
    """Run one pattern search in-process. Returns (tile_ids, info) or None."""
    if a.pattern == 1:
        return pat_teengine(ctx, a, want_fail=(a.fail_rate if a.fail_rate is not None else 0.90),
                            metric=a.metric, label="trap")
    if a.pattern == 2:
        return pat_teengine(ctx, a, structural=_make_structural(ctx, a.triple_frac), label="easytop")
    if a.pattern == 3:
        return pat_bridge(ctx, a)
    if a.pattern == 4:
        return pat_custom_clear(ctx, a)
    if a.pattern == 5:
        return pat_guided(ctx, a)
    return pat_teengine(ctx, a, label="score")               # 6


def _worker(payload):
    """multiprocessing worker: seed its own RNG, run its slice of attempts. The attempts are independent,
    so N workers each searching with a distinct seed ≈ N× faster to the first hit."""
    ctx, a, seed = payload
    random.seed(seed)
    try:
        return run_pattern(ctx, a)
    except SystemExit:                                        # e.g. no 6a+3b config on a tiny board
        return None


# ───────────────────────────────── main ─────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Generate a level by design pattern (1-6) on any layout.")
    ap.add_argument("--pattern", type=int, required=True, choices=range(1, 7))
    ap.add_argument("--layout", required=True, help="bare id (L20), filename, or path")
    ap.add_argument("--out", default="")
    ap.add_argument("--attempts", type=int, default=2000, help="rejection-sampler budget (default 2000)")
    ap.add_argument("--workers", type=int, default=1,
                    help="parallel processes (default 1). >1 splits attempts across workers, first hit wins")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--color-count", type=int, default=None,
                    help="SEED the engine color_count (P1/P2/P6; final n_types may shift after ÷3 repair)")
    ap.add_argument("--score-min", type=float, default=None, help="enable score gate (OFF by default)")
    ap.add_argument("--score-max", type=float, default=None)
    ap.add_argument("--metric", choices=("greedy", "random"), default="greedy", help="P1 fail metric")
    ap.add_argument("--fail-rate", type=float, default=None, help="min player fail rate (default P1 0.90 / P4,P5 0.80)")
    ap.add_argument("--clear-min", type=float, default=None, help="min avg-cleared fraction (default P4 0.40 / P5 0.20)")
    ap.add_argument("--clear-max", type=float, default=None, help="max avg-cleared fraction (default P4 0.60 / P5 0.50)")
    ap.add_argument("--triple-frac", type=float, default=0.85, help="P2 top-half easy fraction")
    ap.add_argument("--bridge-types", type=int, default=None, help="P3 # of bridge types (else by variant)")
    ap.add_argument("--variant", choices=("easy", "harder", "hard"), default="easy", help="P3 difficulty tier")
    ap.add_argument("--raw-ids", action="store_true",
                    help="emit raw sequential type ids (i=tid+1) instead of remapping to real Group_1 art ids")
    ap.add_argument("--allow-trim", action="store_true",
                    help="if the layout isn't %%3==0, accept dropping cells to partition cleanly "
                         "(default: hard-fail -- see _load_trimmed docstring). Recorded in output metadata.")
    a = ap.parse_args()

    random.seed(a.seed)
    path = _resolve_layout(a.layout)
    positions, n_layers, trim_info = _load_trimmed(path, allow_trim=a.allow_trim)  # deterministic (seeded above)
    bb, bc = _build_bb(positions)
    n = len(positions)
    ctx = {"positions": positions, "bb": bb, "bc": bc, "n": n, "n_layers": n_layers}
    workers = max(1, a.workers)
    print(f"layout={os.path.basename(path)}  cells={n} (÷3)  layers={n_layers}  pattern={a.pattern}  "
          f"attempts={a.attempts}  workers={workers}  score_gate={'on' if (a.score_min or a.score_max) else 'OFF'}",
          flush=True)
    if a.pattern == 6 and a.score_min is None and a.score_max is None:
        print("  WARN: pattern 6 with NO --score-min/--score-max -> trivially EASY level (see SKILL sec.4).", flush=True)

    if workers > 1:
        import math
        from multiprocessing import Pool
        per = max(1, math.ceil(a.attempts / workers))        # split the budget across workers
        payloads = [(ctx, argparse.Namespace(**{**vars(a), "attempts": per}), a.seed + 1 + i * 7919)
                    for i in range(workers)]
        res = None
        with Pool(workers) as pool:
            for r in pool.imap_unordered(_worker, payloads):
                if r is not None:                            # first worker to hit wins; stop the rest
                    res = r
                    pool.terminate()
                    break
    else:
        res = run_pattern(ctx, a)

    if res is None:
        print(f"NO candidate in {a.attempts} attempts — raise --attempts, widen/disable the score band, "
              f"or relax --fail-rate/--clear-*.", flush=True)
        return 1
    tile_ids, info = res
    id_map, arted = _id_map(tile_ids, a.raw_ids)
    info["art_ids"] = "Group_1 (85,142-170)" if arted else "raw (tid+1)"
    if not a.raw_ids and not arted:
        print(f"  NOTE: {len(set(tile_ids))} types > {len(VALID_GROUP1_IDS)} Group_1 art ids -> raw ids", flush=True)
    layout_name = os.path.basename(path)
    if trim_info is not None:
        # geometry differs from the named layout -- never claim the pristine name (Task 1: no silent
        # Layout_A -> Layout_A1). Suffix makes the drift visible in every downstream consumer.
        layout_name = f"{layout_name}+trim{trim_info['dropped_cells']}"
    meta = {"source": f"gen_pattern_{info['pattern']}", **info, "layout": layout_name}
    if trim_info is not None:
        meta["geometry_trimmed"] = {"from_layout": os.path.basename(path), **trim_info}
    data = _to_game_json(positions, tile_ids, meta, id_map)
    out = a.out or os.path.join(os.getcwd(),
                                f"Level_P{a.pattern}_{os.path.basename(path).replace('NewLayout_', '').replace('.json', '')}.json")
    json.dump(data, open(out, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {out}", flush=True)
    print(f"   {info}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
