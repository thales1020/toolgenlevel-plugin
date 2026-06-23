"""Training-Free GRPO round runner for layout generation.

This script is the CODE half of the interactive TF-GRPO loop:
  1. Loads real competitor boards (reward ground-truth distribution).
  2. Generates G layouts using the current policy (empirical_gen).
  3. Scores each with per-feature distance from real distribution.
  4. Ranks layouts: winners (close to real) vs losers (far from real).
  5. Prints a structured report for Claude Code to read.

Claude Code is the frozen LLM policy and the experience extractor.
After reading this report, Claude Code updates EXPERIENCES.md
(Add/Modify/Delete/Keep) — that IS the Training-Free GRPO update step.

Usage:
  python run_grpo_round.py --boards <path-to-boards-dir-or-zip> [--G 5] [--round 1]

boards: directory of real board JSON files, OR path to boards_Full.zip.
        Tip: extract refs/boards_Full.zip once:
          python -c "import zipfile; zipfile.ZipFile('refs/boards_Full.zip').extractall('data/boards')"
        Then pass --boards data/boards/<subdir>
"""
import sys, os, json, glob, argparse, random, statistics, math, collections, zipfile, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import empirical_gen


# ── Feature extraction (same as validate_prior.py) ─────────────────────────

def board_cells(d):
    out = []
    for ly in d.get("layers", []):
        L = ly.get("layer", ly.get("index"))
        for c in ly.get("cells", ly.get("stones", [])):
            try:
                out.append((L, float(c["x"]), float(c["y"])))
            except (ValueError, KeyError, TypeError):
                pass
    return out


def feats(cells):
    by = collections.defaultdict(list)
    for L, x, y in cells:
        by[L].append((x, y))
    base = by.get(0, [])
    if len(base) < 3:
        return None
    bxs = [p[0] for p in base]; bys = [p[1] for p in base]
    bw = int(round(max(bxs) - min(bxs))) + 1
    bh = int(round(max(bys) - min(bys))) + 1
    fill = len(base) / (bw * bh)
    # clusters
    bset = {(round(x), round(y)) for x, y in base}; seen_c = set(); ncomp = 0
    for c in bset:
        if c in seen_c:
            continue
        ncomp += 1; st = [c]; seen_c.add(c)
        while st:
            x, y = st.pop()
            for nb in ((x+1,y),(x-1,y),(x,y+1),(x,y-1)):
                if nb in bset and nb not in seen_c:
                    seen_c.add(nb); st.append(nb)
    # tower mean
    up = [(x, y) for L, x, y in cells if L > 0]
    towers = [sum(1 for (x, y) in up if abs(x-bx) < 1 and abs(y-by_) < 1)
              for (bx, by_) in base]
    # h-symmetry
    g = [[0]*bw for _ in range(bh)]
    for x, y in base:
        g[int(round(max(bys)-y))][int(round(x-min(bxs)))] = 1
    sym = 1.0 if g == [r[::-1] for r in g] else 0.0
    # layout difficulty
    from tile_level_simulator import Board, Layer, Cell, DifficultyScorer
    b = Board("f")
    for L in sorted(by):
        ly = Layer(L)
        for (x, y) in by[L]:
            cc = Cell(x, y, L); cc.tile_id = -1; ly.cells.append(cc)
        b.layers.append(ly)
    diff = DifficultyScorer.layout_score(DifficultyScorer.compute_resolve_scores(b))
    return {"n_layers": len(by), "cells": len(cells), "base_fill": round(fill, 3),
            "tower_mean": round(statistics.mean(towers), 2) if towers else 0,
            "n_clusters": ncomp, "sym_h": sym, "aspect": round(bw/bh, 2),
            "layout_diff": round(diff, 2)}


FEATURES = ["n_layers", "cells", "base_fill", "tower_mean", "n_clusters", "sym_h", "aspect", "layout_diff"]


def load_real_boards(boards_path, max_boards=2000, seed=42):
    """Load real boards from a directory or zip file, returning list of cell-sets."""
    rng = random.Random(seed)
    files = []
    tmp_dir = None

    if boards_path.endswith(".zip"):
        tmp_dir = tempfile.mkdtemp(prefix="grpo_boards_")
        with zipfile.ZipFile(boards_path) as z:
            z.extractall(tmp_dir)
        for root, _, fnames in os.walk(tmp_dir):
            for f in fnames:
                if f.endswith(".json"):
                    files.append(os.path.join(root, f))
    else:
        files = sorted(glob.glob(os.path.join(boards_path, "**", "*.json"), recursive=True))
        files += sorted(glob.glob(os.path.join(boards_path, "*.json")))
        files = sorted(set(files))

    if not files:
        raise FileNotFoundError(f"No JSON files found in {boards_path}")

    # dedup by signature
    seen = {}; distinct = []
    for f in files:
        try:
            d = json.load(open(f, encoding="utf-8"))
            cs = board_cells(d)
            if len(cs) < 6:
                continue
            sig = frozenset((L, round(x, 1), round(y, 1)) for L, x, y in cs)
            if sig not in seen:
                seen[sig] = 1; distinct.append(cs)
        except Exception:
            continue

    rng.shuffle(distinct)
    result = distinct[:max_boards]
    return result, tmp_dir


def compute_real_stats(real_cells_list):
    """Compute per-feature mean and std over real boards."""
    all_f = [f for f in (feats(c) for c in real_cells_list) if f]
    stats = {}
    for k in FEATURES:
        vals = [f[k] for f in all_f]
        mu = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 1.0
        p10 = sorted(vals)[max(0, int(len(vals)*0.10))]
        p50 = statistics.median(vals)
        p90 = sorted(vals)[min(len(vals)-1, int(len(vals)*0.90))]
        stats[k] = {"mu": round(mu,3), "sd": round(sd,3),
                    "p10": round(p10,3), "p50": round(p50,3), "p90": round(p90,3)}
    return stats, all_f


def score_layout(f, real_stats):
    """Score a single layout: fraction of features within 1.5σ of real distribution.
    Returns (score 0-1, per_feature_verdict dict)."""
    verdict = {}
    match = 0
    for k in FEATURES:
        if f is None:
            verdict[k] = "FAIL"
            continue
        mu = real_stats[k]["mu"]; sd = real_stats[k]["sd"]
        z = abs(f[k] - mu) / (sd if sd > 0 else 1e-6)
        ok = z <= 1.5
        verdict[k] = "ok" if ok else f"off ({f[k]:.2f} vs real {mu:.2f}±{sd:.2f})"
        if ok:
            match += 1
    return match / len(FEATURES), verdict


def ks2(a, b):
    """2-sample KS statistic."""
    a = sorted(a); b = sorted(b); na, nb = len(a), len(b)
    allv = sorted(set(a + b)); d = 0.0; i = j = 0
    for v in allv:
        while i < na and a[i] <= v: i += 1
        while j < nb and b[j] <= v: j += 1
        d = max(d, abs(i/na - j/nb))
    return d


# ── Main round ──────────────────────────────────────────────────────────────

def run_round(boards_path, G=5, round_num=1, seed=None, save_dir=None):
    seed = seed or (round_num * 17)
    rng = random.Random(seed)

    print(f"\n{'='*60}")
    print(f"  Training-Free GRPO  |  Round {round_num}  |  G={G}")
    print(f"{'='*60}")

    # 1. Load real boards
    print(f"\n[1] Loading real boards from: {boards_path}")
    real_cells, tmp_dir = load_real_boards(boards_path, seed=seed)
    print(f"    {len(real_cells)} distinct real boards loaded")
    real_stats, real_feats = compute_real_stats(real_cells)
    print(f"    Real distribution (medians): " +
          ", ".join(f"{k}={real_stats[k]['p50']}" for k in FEATURES))

    # 2. Generate G rollouts
    print(f"\n[2] Generating G={G} layout rollouts (empirical_gen, current policy)...")
    rollouts = []
    for i in range(G):
        cells = None
        for _ in range(20):
            cells = empirical_gen.sample(rng)
            if cells:
                break
        f = feats(cells) if cells else None
        score, verdict = score_layout(f, real_stats)
        rollouts.append({"idx": i+1, "cells": cells, "feats": f, "score": score, "verdict": verdict})
        status = f"score={score:.2f} ({int(score*len(FEATURES))}/{len(FEATURES)} features match)"
        print(f"    rollout {i+1}: {status}")

    # 3. Rank rollouts
    rollouts.sort(key=lambda r: r["score"], reverse=True)
    winner = rollouts[0]; loser = rollouts[-1]
    scores = [r["score"] for r in rollouts]
    has_variance = (max(scores) - min(scores)) > 0.1

    # 4. Group KS (all G layouts vs real held-out sample)
    print(f"\n[3] Group KS (G={G} generated vs {min(len(real_feats),200)} real):")
    real_sample = real_feats[:200]
    crit = 1.36 * math.sqrt((len(real_sample) + G) / (len(real_sample) * G))
    ks_results = {}
    for k in FEATURES:
        rv = [f[k] for f in real_sample]; gv = [r["feats"][k] for r in rollouts if r["feats"]]
        if not gv:
            continue
        d = ks2(rv, gv)
        ks_results[k] = d
    n_match = sum(1 for d in ks_results.values() if d < crit)
    print(f"    critical@p=0.05 = {crit:.3f}")
    print(f"    {'feature':<13}{'KS':>6}  {'real p50':>10}{'gen p50':>10}  verdict")
    gv_all = {k: [r["feats"][k] for r in rollouts if r["feats"]] for k in FEATURES}
    for k in FEATURES:
        d = ks_results.get(k, 999)
        rm = real_stats[k]["p50"]
        gm = round(statistics.median(gv_all[k]), 3) if gv_all.get(k) else "N/A"
        v = "match" if d < crit else ("close" if d < crit*1.5 else "TELL")
        print(f"    {k:<13}{d:>6.3f}  {rm:>10}{gm:>10}  {v}")
    print(f"\n    SUMMARY: {n_match}/{len(FEATURES)} features indistinguishable from real")

    # 5. Winner vs Loser comparison
    print(f"\n[4] Winner vs Loser comparison:")
    print(f"    {'feature':<13}{'winner':>10}{'loser':>10}{'real p50':>10}  diff")
    diff_features = []
    for k in FEATURES:
        wv = winner["feats"][k] if winner["feats"] else "N/A"
        lv = loser["feats"][k] if loser["feats"] else "N/A"
        rp = real_stats[k]["p50"]
        diff = abs(wv - lv) if isinstance(wv, float) and isinstance(lv, float) else 0
        marker = " <-- key diff" if diff > real_stats[k]["sd"] * 0.5 else ""
        print(f"    {k:<13}{str(wv):>10}{str(lv):>10}{rp:>10.2f}{marker}")
        if marker:
            diff_features.append(k)

    # 6. Save round result
    result = {
        "round": round_num, "G": G, "seed": seed,
        "ks_summary": {k: round(v,4) for k,v in ks_results.items()},
        "n_match": n_match, "n_features": len(FEATURES),
        "rollouts": [{"idx": r["idx"], "score": r["score"],
                      "feats": r["feats"], "verdict": r["verdict"]} for r in rollouts],
        "winner_idx": winner["idx"], "loser_idx": loser["idx"],
        "has_variance": has_variance,
    }
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        out_path = os.path.join(save_dir, f"round_{round_num:02d}_result.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\n    Saved to: {out_path}")

    # 7. Critique prompt for Claude Code
    print(f"\n{'='*60}")
    print(f"  CLAUDE CODE ACTION REQUIRED")
    print(f"{'='*60}")
    if not has_variance:
        print("\n  All rollouts scored similarly (no variance). KEEP experiences unchanged.")
        print("  Suggestion: try a different seed (--seed <N>) or increase G.")
    else:
        print(f"\n  Winner (rollout {winner['idx']}, score={winner['score']:.2f}) features:")
        for k in FEATURES:
            wv = winner["feats"][k] if winner["feats"] else "N/A"
            rp = real_stats[k]["p50"]
            ok = "ok" if winner["verdict"].get(k,"") == "ok" else "off"
            print(f"    {k:<13} = {wv}  (real_p50={rp}, {ok})")

        print(f"\n  Loser  (rollout {loser['idx']}, score={loser['score']:.2f}) features:")
        for k in FEATURES:
            lv = loser["feats"][k] if loser["feats"] else "N/A"
            rp = real_stats[k]["p50"]
            ok = "ok" if loser["verdict"].get(k,"") == "ok" else "off"
            print(f"    {k:<13} = {lv}  (real_p50={rp}, {ok})")

        print(f"\n  Key differentiating features: {', '.join(diff_features) if diff_features else '(none clear)'}")
        print(f"\n  GRPO instruction (paper step 2→3):")
        print(f"    1. Review winner vs loser above.")
        print(f"    2. Identify WHY winner is closer to real distribution.")
        print(f"    3. Extract the NL semantic advantage.")
        print(f"    4. Update EXPERIENCES.md (Add/Modify/Delete/Keep).")
        print(f"       - Add:    new rule if winner uses a pattern not in EXPERIENCES")
        print(f"       - Modify: strengthen/clarify an existing rule")
        print(f"       - Delete: remove a rule that correlates with loser behavior")
        print(f"       - Keep:   leave unchanged if no clear signal")
        print(f"\n  Open EXPERIENCES.md to update:")
        skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(f"    {os.path.join(skill_root, 'EXPERIENCES.md')}")

    if tmp_dir:
        import shutil; shutil.rmtree(tmp_dir, ignore_errors=True)

    return result


def main():
    ap = argparse.ArgumentParser(description="TF-GRPO round runner for layout generation")
    ap.add_argument("--boards", required=True,
                    help="Path to real boards directory or boards_Full.zip")
    ap.add_argument("--G", type=int, default=5, help="Group size (rollouts per round, default 5)")
    ap.add_argument("--round", type=int, default=1, help="Round number (for bookkeeping)")
    ap.add_argument("--seed", type=int, default=0, help="RNG seed (0 = auto from round)")
    ap.add_argument("--save-dir", default="", help="Directory to save round results JSON")
    a = ap.parse_args()
    run_round(
        boards_path=a.boards,
        G=a.G,
        round_num=a.round,
        seed=a.seed or None,
        save_dir=a.save_dir or None,
    )


if __name__ == "__main__":
    main()
