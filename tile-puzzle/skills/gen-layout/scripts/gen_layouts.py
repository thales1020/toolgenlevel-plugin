"""Industrial layout-gen driver (branch A) — bulk EMPTY layouts, fully auto-gated.

Pipeline per candidate (NO human, NO persona, NO solvability — layouts are empty):
  sample family+params+transform  -> grid
  uniform_stagger build @ depth    -> cells   (depth tuned to hit layout-difficulty band)
  STRUCTURAL gate                  -> div3 / no-floating / capacity / pickable
  LAYOUT-DIFFICULTY band gate      -> layout_score (geometry 0-12) in [dmin,dmax]
  DEDUP                            -> exact + coarse-near-dup signatures
  -> keep, export NewLayout_*.json + manifest.json

Human-in-loop is OUTSIDE this script: review a sample + outliers from the manifest.

Usage:
  python gen_layouts.py --n 100 --dmin 6 --dmax 8 --out out/pool [--seed 1]
  python gen_layouts.py --n 1000 --dmin 3 --dmax 10 --out out/pool1k
"""
import sys, os, json, random, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import shape_factory as SF
import layout_builder as LB
from mask_to_layout import trim_to_mult3, center, to_stones
from tile_level_simulator import Board, Layer, Cell, DifficultyScorer


def to_board(cells):
    b = Board("c"); by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            c = Cell(x, y, L); c.tile_id = -1; ly.cells.append(c)
        b.layers.append(ly)
    return b


def layout_diff(cells):
    b = to_board([(c[0], c[1], c[2]) for c in cells])
    return DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))


def _overlap(ax, ay, bx, by):
    return max(0.0, 1.0 - abs(ax - bx)) * max(0.0, 1.0 - abs(ay - by))


def structural_ok(cells):
    """div3, pickable>=3, no floating. No-floating uses the GAME's cover rule: an upper cell
    must OVERLAP >=1 cell directly below (|dx|<1 & |dy|<1) — NOT a 0.5-area guard (which forbade
    real single-cell +0.5 towers; 72% of real upper cells sit on a corner = 0.25 overlap). Cells=[(L,x,y)]."""
    n = len(cells)
    if n < 6 or n % 3 != 0:
        return False
    by = {}
    for L, x, y in cells:
        by.setdefault(L, []).append((x, y))
    # no-floating: must rest on >=1 overlapping cell in the layer directly below
    for L, x, y in cells:
        if L == 0:
            continue
        if not any(abs(x - bx) < 1 and abs(y - by_) < 1 for (bx, by_) in by.get(L - 1, [])):
            return False
    # pickable: a cell with no higher-layer cell covering it
    cl = list(cells)
    pickable = 0
    for (L, x, y) in cl:
        covered = any(L2 > L and abs(x2 - x) < 1 and abs(y2 - y) < 1 for (L2, x2, y2) in cl)
        if not covered:
            pickable += 1
        if pickable >= 3:
            break
    return pickable >= 3


def build_in_band(grid, dmin, dmax, max_layers=8, keep_upper=1.0, seed=0):
    """Build uniform_stagger, choosing depth + top-trim so layout_score lands in [dmin,dmax].
    keep_upper<1 thins upper layers (calibrated 0.9 for the real_match family — see LAYOUT_PRIORS)."""
    chosen = None
    for L in range(2, max_layers + 1):
        cells = [[a, b, c] for (a, b, c) in LB.build(grid, mode="uniform_stagger", max_layers=L,
                                                     keep_upper=keep_upper, seed=seed)]
        if len(cells) < 12:
            continue
        d = layout_diff(cells)
        chosen = (cells, d)
        if d >= dmin:
            break
    if chosen is None:
        return None
    cells, d = chosen
    # overshoot -> trim top-layer cells (farthest from origin) in small batches until <= dmax
    guard = 0
    while d > dmax and guard < 400:
        top = max(c[0] for c in cells)
        tops = [c for c in cells if c[0] == top]
        if len(tops) <= 1:
            break
        tops.sort(key=lambda c: -(c[1] ** 2 + c[2] ** 2))
        for v in tops[:max(1, len(tops) // 12)]:
            cells.remove(v)
        d = layout_diff(cells); guard += 1
    cells, _ = trim_to_mult3(cells)
    cells = center(cells)
    d = layout_diff(cells)
    return cells, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["empirical", "abstract", "compose", "symmetric", "mixed"], default="empirical",
                    help="empirical=sample real skeletons (default, 7/8 KS match); "
                         "abstract=parametric families; "
                         "compose=Claude-authored spec via claude_compose; "
                         "symmetric=exact-h-symmetric bulk via component crossover (gen_symmetric); "
                         "mixed=distribution-correct ~64%% symmetric + ~36%% clean-asymmetric")
    ap.add_argument("--bank-limit", type=int, default=0,
                    help="symmetric/mixed mode: cap source boards when mining from zip (0=use bundled cache)")
    ap.add_argument("--sym-frac", type=float, default=0.64,
                    help="mixed mode: fraction of exact-symmetric layouts (default 0.64, real-board rate)")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--dmin", type=float, default=6.0)
    ap.add_argument("--dmax", type=float, default=8.0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-attempts", type=int, default=0, help="0 = n*40")
    ap.add_argument("--name", default="", help="layout name for compose mode")
    ap.add_argument("--spec", default="", help="compose mode: JSON list of [x,y,height] anchors")
    ap.add_argument("--mirror", action="store_true", default=True,
                    help="compose mode: apply h-symmetry mirror (default True)")
    ap.add_argument("--no-mirror", dest="mirror", action="store_false")
    # legacy flags (kept for backwards compat)
    ap.add_argument("--abstract-flag", dest="_abstract", action="store_true")
    ap.add_argument("--match-real", action="store_true")
    ap.add_argument("--exclude-zip", default="",
                    help="Path to a zip of real boards to exclude (exact-signature match). "
                         "Prevents generating layouts identical to any board in the zip.")
    a = ap.parse_args()

    # compose mode: Claude-authored spec -> rendered layout
    if a.mode == "compose":
        import claude_compose as CC
        os.makedirs(a.out, exist_ok=True)
        if not a.spec:
            print("ERROR: --mode compose requires --spec '[x,y,h],[...]'")
            return
        try:
            spec = json.loads(a.spec)
        except json.JSONDecodeError as e:
            print(f"ERROR: --spec must be valid JSON: {e}")
            return
        cells = CC.compose(spec, mirror=a.mirror)
        if not cells:
            print("ERROR: compose() returned empty cell list (check spec + support rules)")
            return
        name = a.name or "compose_layout"
        data = to_stones([list(c) for c in cells], name)
        d = layout_diff(cells)
        data["metadata"]["layout_difficulty"] = round(d, 2)
        data["metadata"]["source"] = "claude_compose"
        out_path = os.path.join(a.out, f"NewLayout_{name}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        print(f"compose -> {out_path}  ({len(cells)} cells, {max(c[0] for c in cells)+1} layers, layout_diff={d:.2f})")
        return

    # symmetric mode: exact-h-symmetric bulk via component crossover (gen_symmetric).
    # Guarantees sym_h==1.0 BY CONSTRUCTION instead of empirical's perturb-then-hope, which breaks
    # symmetry at the tower-trim + support-cleanup + div3 steps (-> "gần đối xứng" ugly output).
    if a.mode == "symmetric":
        import gen_symmetric as GS
        GS.generate(a.n, a.out, seed=a.seed, bank_limit=a.bank_limit or None)
        return

    # mixed mode: ~sym_frac exact-symmetric + the rest clean-asymmetric -> matches the real
    # ~64% h-symmetric distribution without empirical's perturb-induced jaggedness.
    if a.mode == "mixed":
        import gen_symmetric as GS
        GS.generate_mixed(a.n, a.out, seed=a.seed, sym_frac=a.sym_frac, bank_limit=a.bank_limit or None)
        return

    os.makedirs(a.out, exist_ok=True)
    rng = random.Random(a.seed)
    match_real = a.mode == "empirical" or (a.match_real and a.mode != "abstract")
    import empirical_gen as real_gen                   # data-driven generator (7/8 KS-indistinguishable)
    fams = list(SF.FAMILIES.keys()) if a.mode == "abstract" else ["real_match"]
    keep_upper = 1.0 if a.mode == "abstract" else 0.9
    max_attempts = a.max_attempts or a.n * 40

    seen_exact = set(); seen_coarse = set()

    # load pre-computed exclusion hashes (bundled in skill, self-contained)
    import hashlib as _hl
    _skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _sigs_path = os.path.join(_skill_root, "excluded_sigs.json")
    _excluded_hashes = set()
    if os.path.exists(_sigs_path):
        _excluded_hashes = set(json.load(open(_sigs_path, encoding="utf-8")))

    def _sig_hash(cells):
        key = sorted((L, round(x, 1), round(y, 1)) for L, x, y in cells)
        return _hl.md5(str(key).encode()).hexdigest()

    # fallback: also load from boards_Full.zip if --exclude-zip given explicitly
    if a.exclude_zip:
        import zipfile as _zf, tempfile as _tmp, shutil as _sh
        print(f"Loading extra exclusions from: {a.exclude_zip}")
        _tdir = _tmp.mkdtemp()
        try:
            with _zf.ZipFile(a.exclude_zip) as _z: _z.extractall(_tdir)
            import glob as _glob
            for _f in [os.path.join(r, f) for r, _, fs in os.walk(_tdir) for f in fs if f.endswith(".json")]:
                try:
                    _d = json.load(open(_f, encoding="utf-8"))
                    _cs = []
                    for _ly in _d.get("layers", []):
                        _L = _ly.get("index", _ly.get("layer", 0))
                        for _s in _ly.get("stones", _ly.get("cells", [])):
                            try: _cs.append((_L, float(_s["x"]), float(_s["y"])))
                            except: pass
                    if _cs: _excluded_hashes.add(_sig_hash(_cs))
                except: pass
        finally:
            _sh.rmtree(_tdir, ignore_errors=True)

    kept = []; attempts = 0
    reasons = {"struct": 0, "band": 0, "dup": 0, "build": 0}
    while len(kept) < a.n and attempts < max_attempts:
        attempts += 1
        if match_real:
            cells = real_gen.sample(rng)
            if not cells:
                reasons["build"] += 1; continue
            cells = [list(c) for c in cells]
            d = layout_diff(cells)
        else:
            fam = rng.choice(fams)
            grid = SF.FAMILIES[fam](rng)
            tname = rng.choice(SF.TRANSFORMS)
            grid = SF.apply_transform(grid, tname, rng)
            res = build_in_band(grid, a.dmin, a.dmax, keep_upper=keep_upper, seed=a.seed * 1000 + attempts)
            if res is None:
                reasons["build"] += 1; continue
            cells, d = res
            if not (a.dmin - 0.2 <= d <= a.dmax + 0.2):
                reasons["band"] += 1; continue
        ctup = [(c[0], c[1], c[2]) for c in cells]
        if not structural_ok(ctup):
            reasons["struct"] += 1; continue
        cov = LB.coverage_histogram(ctup)
        ex = SF.exact_sig(ctup); co = SF.coarse_sig(ctup, cov)
        if ex in seen_exact or co in seen_coarse:
            reasons["dup"] += 1; continue
        if _excluded_hashes and _sig_hash(ctup) in _excluded_hashes:
            reasons["dup"] += 1; continue
        seen_exact.add(ex); seen_coarse.add(co)
        idx = len(kept) + 1
        fam = "real_gen" if match_real else fam
        tname = "-" if match_real else tname
        name = f"{fam}_{idx:04d}"
        data = to_stones([list(c) for c in cells], name)
        data["metadata"]["layout_difficulty"] = round(d, 2)
        data["metadata"]["family"] = fam
        data["metadata"]["transform"] = tname
        data["metadata"]["structural_ok"] = True
        with open(os.path.join(a.out, f"NewLayout_{name}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        kept.append({"name": name, "family": fam, "transform": tname,
                     "layout_difficulty": round(d, 2), "total": len(cells),
                     "capacity": len(cells) // 3, "n_layers": max(c[0] for c in cells) + 1,
                     "cov_hist": cov})
        if len(kept) % 25 == 0:
            print(f"  kept {len(kept)}/{a.n}  (attempts {attempts})", flush=True)

    # manifest
    diffs = [k["layout_difficulty"] for k in kept]
    fam_counts = {}
    for k in kept:
        fam_counts[k["family"]] = fam_counts.get(k["family"], 0) + 1
    manifest = {"spec": {"n": a.n, "dmin": a.dmin, "dmax": a.dmax, "seed": a.seed},
                "produced": len(kept), "attempts": attempts,
                "reject_reasons": reasons, "family_counts": fam_counts,
                "diff_min": min(diffs) if diffs else None, "diff_max": max(diffs) if diffs else None,
                "layouts": kept}
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nPRODUCED {len(kept)}/{a.n} in {attempts} attempts -> {a.out}")
    print(f"  reject reasons: {reasons}")
    print(f"  family spread: {fam_counts}")
    print(f"  diff range: {manifest['diff_min']}..{manifest['diff_max']}")


if __name__ == "__main__":
    main()
