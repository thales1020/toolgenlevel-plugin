# -*- coding: utf-8 -*-
"""
recalibrate.py — hieu chuan lai model winrate-target tu log tho cua mot cohort.

Day la PHAN LOI cua pipeline (truoc kia nam o data-v2/recalibrate_pipeline.py): chi lam
viec cua TOOL — fit theta + refit Tang 3 + ghi winrate_model.json / final_eval_4Y.csv.
KHONG dung toi dashboard (heatmap.html / heatmap_data.json) — do la viec cua project,
van o data-v2/.

  Tang 1 (beta)  : KHONG hieu chuan lai (xem ARCHITECTURE §9 / REFACTOR_PLAN 3.2)
  Tang 2 (theta) : fit lai — pheu song sot + Inverse Mills Ratio
  Tang 3 (heads) : refit lai ca 9 dau Y

CHAY:
  python scripts/recalibrate.py <duong_dan_csv> [--cohort TEN] [--dry-run]
                                [--also-write-root] [--no-cv]

  --cohort           ten cohort ghi vao provenance (mac dinh: ten file csv)
  --dry-run          chay het nhung KHONG ghi file nao — de xem truoc MAE
  --also-write-root  ghi them ban sao ra <project>/analysis/ (tuong thich nguoc)
  --no-cv            bo qua kiem dinh cheo 5-fold (chay nhanh hon)

CSV dau vao can cac cot:
  user_id, level, attempt_num, result, duration_sec,
  undo_used, magnet_used, shuffle_used, revive
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit
from scipy.stats import norm
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import KFold

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---------------------------------------------------------------- duong dan
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)                       # skills/winrate-target
PLUGIN = os.path.dirname(os.path.dirname(SKILL))    # skylink-tile-plugin
PROJECT = os.path.dirname(PLUGIN)

MODEL_PATH = os.path.join(SKILL, "analysis", "winrate_model.json")
EVAL_PATH = os.path.join(SKILL, "analysis", "final_eval_4Y.csv")
CACHE_PATH = os.path.join(SKILL, "data", "cached_level_features.json")

# ban sao cu o project (chi ghi khi --also-write-root)
ROOT_MODEL_PATH = os.path.join(PROJECT, "analysis", "winrate_model.json")
ROOT_EVAL_PATH = os.path.join(PROJECT, "analysis", "final_eval_4Y.csv")

PIPELINE_VERSION = "3.0-plugin"

# Ung vien he so phat cho Ridge. Chon rieng cho TUNG dau bang kiem dinh cheo.
# Vi sao khong dung OLS thuan (LinearRegression): giai doan `early` chi co DUNG 60 level
# (early = L1-60, khong the co them), trong khi model co 37+ tham so -> OLS overfit, va
# do da tung khien vai o co "skill" AM (du bao con te hon viec doan trung binh).
RIDGE_ALPHAS = [0.1, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0]
SEED = 42

# Tham so Gradient Boosting cho TANG 3. Quan he layout->hanh vi la PHI TUYEN: do bang
# kiem dinh cheo, boosting thang Ridge 18/21 o, tong -11.88 diem MAE. Nhung no phai luu
# bang joblib (nhi phan, rang buoc phien ban sklearn) nen khong soi he so bang mat duoc.
# => LUU CA HAI: boosting lam lop chinh (heads_gbm.joblib), Ridge trong JSON lam DU PHONG.
# Chi nhan boosting cho tung dau NEU no thuc su tot hon Ridge tren kiem dinh cheo.
GBM_PARAMS = dict(max_iter=250, learning_rate=0.06, max_depth=4,
                  min_samples_leaf=15, l2_regularization=1.0, random_state=SEED)
GBM_MIN_GAIN = 0.05       # diem MAE toi thieu phai tot hon Ridge moi nhan boosting

# Feature TON KHO tinh tu log (neu CSV co cac cot inventory_*/wallet_coin).
# Ly do them: nguoi choi chi dung booster khi HO CO booster — model cu hoan toan mu
# voi thong tin nay. Chi gan cho cac dau LINEAR (hanh vi kinh te); cac dau sigmoid
# (att1/win_att/near_miss) giu nguyen vat ly theta-beta.
INV_FEATS = ["inv_undo", "inv_magnet", "inv_shuffle", "wallet",
             "pct_has_undo", "pct_has_shuffle", "pct_has_magnet"]
INV_SRC = {"inv_undo": "inventory_undo", "inv_magnet": "inventory_magnet",
           "inv_shuffle": "inventory_shuffle", "wallet": "wallet_coin"}

HEADS_LIST = [
    ("att1",        "sigmoid", "att1"),
    ("win_att",     "sigmoid", "all"),
    ("dur_win1",    "linear",  None),
    ("revive_user", "linear",  None),
    ("booster",     "linear",  None),
    ("near_miss",   "sigmoid", "all"),
    ("undo",        "linear",  None),
    ("shuffle",     "linear",  None),
    ("magnet",      "linear",  None),
]
ACT_KEY = {
    "att1": "act_win1", "win_att": "act_win_att", "near_miss": "act_near_miss",
    "dur_win1": "act_dur", "revive_user": "act_revive", "booster": "act_booster",
    "undo": "act_undo", "shuffle": "act_shuffle", "magnet": "act_magnet",
}
STAGES = ["early", "mid", "late"]


def log(msg, pct=None):
    print(f"[PROGRESS] {pct}% | {msg}" if pct is not None else f"[INFO] {msg}")
    sys.stdout.flush()


def logit(p):
    return np.log(np.clip(p, 0.001, 0.999) / (1.0 - np.clip(p, 0.001, 0.999)))


def inv_logit(x):
    return 1.0 / (1.0 + np.exp(-x))


def get_stage(L):
    return "early" if L <= 60 else ("mid" if L <= 140 else "late")


def estimate_theta_map(results, B0, prior_mean=0.0, prior_std=2.0):
    """MAP 1 tham so cho trinh do 1 nguoi choi (Rasch + prior chuan)."""
    if not results:
        return 0.0
    betas = np.array([r[0] for r in results], dtype=float)
    y = np.array([r[1] for r in results], dtype=float)

    def grad(theta):
        p = 1.0 / (1.0 + np.exp(-(B0 + theta - betas)))
        return np.sum(y - p) - (theta - prior_mean) / (prior_std ** 2)

    lo, hi = -10.0, 10.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if grad(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def build_feature_target(ld, head_name, use_inv=False):
    """Dung (X, y) cho 1 dau. Tra ve (feat, target, offset|None).

    Dau sigmoid: [x, beta, offset]        (giu nguyen — vat ly theta-beta)
    Dau linear : [x, beta] (+ ton kho)    (hanh vi kinh te — phu thuoc viec CO booster)"""
    x, beta = ld["x"], ld["beta"]
    if head_name == "att1":
        off = ld["off_att1"]
        return np.concatenate([x, [beta, off]]), logit(ld["act_win1"] / 100.0) - off, off
    if head_name == "win_att":
        off = ld["off_win_att"]
        return np.concatenate([x, [beta, off]]), logit(ld["act_win_att"] / 100.0) - off, off
    if head_name == "near_miss":
        off = ld["off_win_att"]
        return np.concatenate([x, [beta, off]]), logit(ld["act_near_miss"] / 100.0) - off, off
    tail = [beta] + (list(ld.get("inv", [])) if use_inv else [])
    return np.concatenate([x, tail]), ld[ACT_KEY[head_name]], None


def fit_ridge_cv(X, Y, sw, seed=SEED):
    """Chon alpha bang kiem dinh cheo 5-fold, roi fit lai tren toan bo. Tra (model, alpha)."""
    if len(Y) < 25:
        return LinearRegression().fit(X, Y, sample_weight=sw), 0.0
    best = None
    for a in RIDGE_ALPHAS:
        oof = np.zeros(len(Y))
        for tr, te in KFold(n_splits=5, shuffle=True, random_state=seed).split(X):
            oof[te] = Ridge(alpha=a).fit(X[tr], Y[tr], sample_weight=sw[tr]).predict(X[te])
        err = float(np.average(np.abs(Y - oof), weights=sw))
        if best is None or err < best[0]:
            best = (err, a)
    a = best[1]
    return Ridge(alpha=a).fit(X, Y, sample_weight=sw), a


def fit_gbm_cv(X, Y, sw, seed=SEED):
    """Fit Gradient Boosting + tra MAE kiem dinh cheo (co trong so) de so voi Ridge."""
    oof = np.zeros(len(Y))
    for tr, te in KFold(n_splits=5, shuffle=True, random_state=seed).split(X):
        oof[te] = (HistGradientBoostingRegressor(**GBM_PARAMS)
                   .fit(X[tr], Y[tr], sample_weight=sw[tr]).predict(X[te]))
    err = float(np.average(np.abs(Y - oof), weights=sw))
    return HistGradientBoostingRegressor(**GBM_PARAMS).fit(X, Y, sample_weight=sw), err, oof


def ridge_cv_err(X, Y, sw, alpha, seed=SEED):
    """MAE kiem dinh cheo cua Ridge o alpha da chon — de so cong bang voi GBM."""
    oof = np.zeros(len(Y))
    for tr, te in KFold(n_splits=5, shuffle=True, random_state=seed).split(X):
        oof[te] = Ridge(alpha=alpha).fit(X[tr], Y[tr], sample_weight=sw[tr]).predict(X[te])
    return float(np.average(np.abs(Y - oof), weights=sw))


def stage_mae(levels_data, idx_list, preds, head_name, kind):
    """MAE theo giai doan, quy nguoc ve don vi that (% hoac phut)."""
    out = {}
    for stage in STAGES:
        sel = [i for i, gi in enumerate(idx_list) if levels_data[gi]["stage"] == stage]
        if not sel:
            continue
        act = [levels_data[idx_list[i]][ACT_KEY[head_name]] for i in sel]
        if kind == "sigmoid":
            pred = []
            for i in sel:
                ld = levels_data[idx_list[i]]
                off = ld["off_att1"] if head_name == "att1" else ld["off_win_att"]
                pred.append(inv_logit(preds[i] + off) * 100.0)
        else:
            pred = [preds[i] for i in sel]
        out[stage] = float(mean_absolute_error(act, pred))
    return out


def run(csv_path, cohort_name=None, dry_run=False, also_root=False, do_cv=True,
        balance=True, use_gbm=True):
    log("Bat dau hieu chuan (phan loi, trong plugin)...", 0)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Khong thay CSV dau vao: {csv_path}")
    if not os.path.exists(CACHE_PATH):
        raise FileNotFoundError(
            f"Khong thay cache feature: {CACHE_PATH}\n"
            f"  -> chep tu data-v2/cached_level_features.json sang do."
        )
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Khong thay model: {MODEL_PATH}")

    cohort_name = cohort_name or os.path.splitext(os.path.basename(csv_path))[0]

    cached = {it["level"]: it for it in json.load(open(CACHE_PATH, encoding="utf-8"))}
    log(f"Cache feature: {len(cached)} level.", 5)

    M = json.load(open(MODEL_PATH, encoding="utf-8"))
    mae_old = json.loads(json.dumps(M.get("MAE_STAGE", {})))   # giu lai de so sanh
    B0 = M["B0"]

    log("Doc log tho...", 10)
    raw = pd.read_csv(csv_path)
    log(f"Log: {raw.shape[0]:,} dong, {raw.user_id.nunique():,} nguoi choi.", 25)

    raw["use_undo"] = (raw["undo_used"] > 0).astype(int)
    raw["use_magnet"] = (raw["magnet_used"] > 0).astype(int)
    raw["use_shuffle"] = (raw["shuffle_used"] > 0).astype(int)
    raw["use_any"] = (raw.use_undo | raw.use_magnet | raw.use_shuffle).astype(int)

    log("Tong hop chi so thuc te theo level...", 30)
    first_att = raw[raw.attempt_num == 1]
    win_rate_1st = first_att.groupby("level")["result"].apply(lambda s: (s == "win").mean() * 100)
    win_att_pct = raw.groupby("level")["result"].apply(lambda s: (s == "win").mean() * 100)
    avg_dur_win = raw[raw.result == "win"].groupby("level")["duration_sec"].mean() / 60.0
    per_user = lambda col: raw.groupby(["level", "user_id"])[col].max().groupby("level").mean() * 100
    revive_pct, booster_pct = per_user("revive"), per_user("use_any")
    undo_pct, shuffle_pct, magnet_pct = per_user("use_undo"), per_user("use_shuffle"), per_user("use_magnet")

    user_wins = raw[raw.result == "win"].groupby(["level", "user_id"])["attempt_num"].min()
    total_users = raw.groupby("level")["user_id"].nunique()
    near_miss_pct = (user_wins[user_wins >= 3].groupby("level").size() / total_users * 100).fillna(0.0)

    # --- TON KHO theo level (chi khi log co cac cot inventory_*/wallet_coin) ---
    has_inv = all(c in raw.columns for c in INV_SRC.values())
    inv_by_level = {}
    if has_inv:
        g = raw.groupby("level")
        cols = {k: g[src].mean() for k, src in INV_SRC.items()}
        for k, src in (("pct_has_undo", "inventory_undo"), ("pct_has_shuffle", "inventory_shuffle"),
                       ("pct_has_magnet", "inventory_magnet")):
            cols[k] = g[src].apply(lambda s: (s > 0).mean() * 100)
        for lvl in cols["inv_undo"].index:
            inv_by_level[int(lvl)] = [float(cols[f].get(lvl, 0.0)) for f in INV_FEATS]
        log(f"Ton kho: tinh duoc cho {len(inv_by_level)} level ({len(INV_FEATS)} feature).", 32)
    else:
        log("Log KHONG co cot inventory_*/wallet_coin -> bo qua feature ton kho.", 32)

    # ---------------------------------------------------- Tang 2: theta / pheu
    log("Uoc luong MAP theta cho tung nguoi choi...", 40)
    level_betas = {lvl: cached[lvl]["beta"] for lvl in cached}
    rv = raw.copy()
    rv["beta"] = rv["level"].map(level_betas)
    rv = rv.dropna(subset=["beta"])
    rv_att1 = rv[rv.attempt_num == 1].copy()
    rv_att1["outcome"] = (rv_att1.result == "win").astype(int)
    rv_all = rv.copy()
    rv_all["outcome"] = (rv_all.result == "win").astype(int)

    def thetas_of(df):
        out = {}
        for uid, g in df.groupby("user_id"):
            res = list(zip(g["beta"], g["outcome"]))
            if len(res) >= 5:
                out[uid] = estimate_theta_map(res, B0)
        return out

    th_att1, th_all = thetas_of(rv_att1), thetas_of(rv_all)
    log(f"MAP xong: {len(th_att1):,} user (att1), {len(th_all):,} user (all).", 55)

    log("Khop pheu song sot (reach decay)...", 65)
    levels_list = sorted(total_users.index.tolist())
    reach_vals = [total_users[l] / total_users[1] for l in levels_list]
    popt, _ = curve_fit(lambda L, a, b: 1.0 / ((1.0 + a * L) ** b),
                        levels_list, reach_vals, p0=[0.02, 2.0], bounds=(0, [1.0, 10.0]))
    reach_a, reach_b = float(popt[0]), float(popt[1])

    rv_att1["theta_u"] = rv_att1["user_id"].map(th_att1)
    rv_all["theta_u"] = rv_all["user_id"].map(th_all)

    stage_pool = {"att1": {s: [] for s in STAGES}, "all": {s: [] for s in STAGES}}
    lvl_mean = {"att1": {}, "all": {}}
    for kind, df in [("att1", rv_att1), ("all", rv_all)]:
        for lvl, g in df.dropna(subset=["theta_u"]).groupby("level"):
            lvl_mean[kind][lvl] = float(g["theta_u"].mean())
            stage_pool[kind][get_stage(lvl)].extend(g["theta_u"].tolist())

    survival = {"reach_a": reach_a, "reach_b": reach_b}
    for kind in ("att1", "all"):
        Xs, Ys = [], []
        for lvl, m_theta in lvl_mean[kind].items():
            r = min(max(total_users[lvl] / total_users[1], 1e-4), 0.9999)
            Xs.append([lvl, norm.pdf(norm.ppf(1.0 - r)) / r])
            Ys.append(m_theta)
        reg = LinearRegression().fit(np.array(Xs), np.array(Ys))
        survival[kind] = {"intercept": float(reg.intercept_),
                          "coef_lvl": float(reg.coef_[0]),
                          "coef_mills": float(reg.coef_[1])}
    log(f"Pheu: Reach = 1/(1 + {reach_a:.5f}*L)^{reach_b:.4f}", 75)

    # seed co dinh -> chay lai cho ket qua giong nhau (truoc day khong co seed)
    # khuon giu nguyen nhu cu: {kind: {"stage": {early/mid/late: [...]}, "level": {}}}
    rng = np.random.default_rng(SEED)
    M["THETA"] = {
        k: {"stage": {s: ([round(float(x), 4) for x in rng.choice(stage_pool[k][s], 1000, replace=True)]
                          if stage_pool[k][s] else [])
                      for s in STAGES},
            "level": {}}
        for k in ("att1", "all")
    }
    M["SURVIVAL_MODEL"] = survival

    # ---------------------------------------------------- Tang 3: refit heads
    log("Refit Tang 3 (9 dau Y)...", 80)
    std_normal = np.random.default_rng(SEED).normal(0.0, 1.0, 1000)

    levels_data = []
    for lvl in levels_list:
        if lvl not in cached or lvl not in win_rate_1st.index:
            continue
        beta = cached[lvl]["beta"]
        r = min(max(total_users[lvl] / total_users[1], 1e-4), 0.9999)
        mills = norm.pdf(norm.ppf(1.0 - r)) / r
        offs = {}
        for kind, key in (("att1", "off_att1"), ("all", "off_win_att")):
            p = survival[kind]
            mu = p["intercept"] + p["coef_lvl"] * lvl + p["coef_mills"] * mills
            std = (max(-0.001776 * lvl + 1.603511, 0.1) if kind == "att1"
                   else max(-0.002056 * lvl + 1.859607, 0.1))
            th = mu + std * std_normal
            offs[key] = logit(float(np.mean(1.0 / (1.0 + np.exp(-(B0 + th - beta))))))
        levels_data.append({
            "level": lvl, "x": np.array(cached[lvl]["x"], dtype=float), "beta": beta,
            "stage": get_stage(lvl), **offs,
            "act_win1": win_rate_1st[lvl], "act_win_att": win_att_pct[lvl],
            "act_dur": avg_dur_win.get(lvl, 1.5), "act_revive": revive_pct.get(lvl, 5.0),
            "act_booster": booster_pct.get(lvl, 10.0), "act_near_miss": near_miss_pct.get(lvl, 5.0),
            "act_undo": undo_pct.get(lvl, 5.0), "act_shuffle": shuffle_pct.get(lvl, 5.0),
            "act_magnet": magnet_pct.get(lvl, 5.0),
            "inv": inv_by_level.get(lvl, [0.0] * len(INV_FEATS)),
        })

    n_stage = {s: sum(1 for ld in levels_data if ld["stage"] == s) for s in STAGES}
    log(f"So level fit duoc: {len(levels_data)} (early {n_stage['early']} / "
        f"mid {n_stage['mid']} / late {n_stage['late']}).")
    if len(levels_data) < 30:
        raise RuntimeError(f"Chi co {len(levels_data)} level — qua it de fit. Kiem tra lai CSV/cohort.")

    new_heads, mae_stage, mae_cv = {}, {}, {}
    gbm_heads, gbm_report = {}, []          # lop phi tuyen (tuy chon, luu joblib rieng)
    all_idx = list(range(len(levels_data)))

    # Trong so mau: khi mot cohort sau, `late` co the chiem >80% so level -> hoi quy bi
    # late chi phoi, keo MAE early/mid TE DI du tong so mau tang. Can bang lai de moi giai
    # doan gop phan ngang nhau. Khuon model KHONG doi (van coef/mean/scale/int) nen
    # winrate_tool.py khong can sua gi.
    if balance:
        sw = np.array([1.0 / max(n_stage[ld["stage"]], 1) for ld in levels_data], dtype=float)
        sw = sw / sw.mean()
        log(f"Can bang trong so theo giai doan: early x{sw[0]:.2f} ... "
            f"(late chiem {n_stage['late']}/{len(levels_data)} mau tho)")
    else:
        sw = np.ones(len(levels_data), dtype=float)

    for head_name, kind, theta_kind in HEADS_LIST:
        use_inv = has_inv and kind == "linear"      # ton kho chi cho dau kinh te
        X, Y = [], []
        for ld in levels_data:
            feat, target, _ = build_feature_target(ld, head_name, use_inv)
            X.append(feat)
            Y.append(target)
        X, Y = np.array(X, dtype=float), np.array(Y, dtype=float)

        mean, scale = X.mean(axis=0), X.std(axis=0)
        scale[scale == 0.0] = 1.0
        reg, alpha = fit_ridge_cv((X - mean) / scale, Y, sw)

        new_heads[head_name] = {
            "kind": kind, "theta_kind": theta_kind,
            "coef": reg.coef_.tolist(), "mean": mean.tolist(),
            "scale": scale.tolist(), "int": float(reg.intercept_),
            "alpha": float(alpha), "uses_inv": bool(use_inv),
        }

        # ── TANG 3 PHI TUYEN: thu Gradient Boosting, chi nhan neu THUC SU tot hon ──
        # GBM fit tren feature THO (cay khong can chuan hoa). So sanh voi Ridge tren
        # CUNG chia fold -> quyet dinh cong bang cho tung dau.
        if use_gbm and len(Y) >= 60:
            g_model, g_err, _ = fit_gbm_cv(X, Y, sw)
            r_err = ridge_cv_err((X - mean) / scale, Y, sw, alpha)
            if g_err < r_err - GBM_MIN_GAIN:
                gbm_heads[head_name] = g_model
                new_heads[head_name]["gbm"] = True
                gbm_report.append((head_name, r_err, g_err, "nhan"))
            else:
                gbm_report.append((head_name, r_err, g_err, "bo (khong hon Ridge)"))
        # MAE phai phan anh LOP THUC SU DUOC DUNG luc du bao, khong phai lop du phong.
        _use_g = head_name in gbm_heads

        # (a) MAE in-sample — giu cach tinh cu de so sanh duoc voi model truoc
        _in_pred = (gbm_heads[head_name].predict(X) if _use_g
                    else reg.predict((X - mean) / scale))
        mae_stage[head_name] = stage_mae(levels_data, all_idx, _in_pred, head_name, kind)

        # (b) MAE kiem dinh cheo 5-fold — trung thuc hon
        if do_cv and len(levels_data) >= 25:
            oof = np.zeros(len(Y))
            for tr, te in KFold(n_splits=5, shuffle=True, random_state=SEED).split(X):
                if _use_g:
                    oof[te] = (HistGradientBoostingRegressor(**GBM_PARAMS)
                               .fit(X[tr], Y[tr], sample_weight=sw[tr]).predict(X[te]))
                else:
                    m2, s2 = X[tr].mean(axis=0), X[tr].std(axis=0)
                    s2[s2 == 0.0] = 1.0
                    _m, _ = fit_ridge_cv((X[tr] - m2) / s2, Y[tr], sw[tr])
                    oof[te] = _m.predict((X[te] - m2) / s2)
            mae_cv[head_name] = stage_mae(levels_data, all_idx, oof, head_name, kind)

    M["HEADS"] = new_heads
    M["MAE_STAGE"] = mae_stage
    if has_inv:
        # luu bang ton kho theo level -> luc du bao level moi se noi suy tu day
        M["INVENTORY"] = {"feats": INV_FEATS,
                          "by_level": {str(k): [round(v, 4) for v in vals]
                                       for k, vals in sorted(inv_by_level.items())}}
    else:
        M.pop("INVENTORY", None)
    if mae_cv:
        M["MAE_STAGE_CV"] = mae_cv
    M["PROVENANCE"] = {
        "source_csv": os.path.abspath(csv_path),
        "cohort": cohort_name,
        "trained_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "n_levels": len(levels_data),
        "n_levels_by_stage": n_stage,
        "n_rows": int(raw.shape[0]),
        "n_users": int(raw.user_id.nunique()),
        "level_min": int(min(ld["level"] for ld in levels_data)),
        "level_max": int(max(ld["level"] for ld in levels_data)),
        "pipeline_version": PIPELINE_VERSION,
        "layers_refit": ["theta (Tang 2)", "heads (Tang 3)"],
        "layers_NOT_refit": ["beta / Tang 1 (FEATS, s1_mean, s1_scale, r1_coef, r1_int)"],
        "stage_balanced": bool(balance),
        "gbm_heads": sorted(gbm_heads.keys()),
        "gbm_note": ("Cac dau nay dung Gradient Boosting (analysis/heads_gbm.joblib); "
                     "he so Ridge trong JSON la DU PHONG khi thieu/khong nap duoc joblib."),
        "regularization": f"Ridge, alpha chon theo CV moi dau trong {RIDGE_ALPHAS}",
        "inventory_features": INV_FEATS if has_inv else [],
        "mae_note": "MAE_STAGE la in-sample (giu cach tinh cu). MAE_STAGE_CV la 5-fold out-of-sample.",
    }
    log("Refit xong.", 90)

    if gbm_report:
        print()
        print("  TANG 3 PHI TUYEN — Gradient Boosting vs Ridge (MAE kiem dinh cheo, co trong so)")
        print(f"    {'dau':<13}{'Ridge':>8}{'GBM':>8}{'loi':>8}   quyet dinh")
        print("    " + "-" * 56)
        for nm, r_e, g_e, dec in gbm_report:
            print(f"    {nm:<13}{r_e:>8.2f}{g_e:>8.2f}{g_e - r_e:>+8.2f}   {dec}")
        print(f"    -> nhan GBM cho {len(gbm_heads)}/{len(gbm_report)} dau")

    _report(mae_old, mae_stage, mae_cv, n_stage)

    if dry_run:
        log("--dry-run: KHONG ghi file nao.", 100)
        return M

    eval_rows = []
    for ld in levels_data:
        row = {"level": ld["level"], "beta": ld["beta"], "stage": ld["stage"],
               "att1": ld["act_win1"], "win_att": ld["act_win_att"], "dur_win1": ld["act_dur"],
               "revive_user": ld["act_revive"], "booster": ld["act_booster"],
               "near_miss_rate_pct": ld["act_near_miss"], "undo": ld["act_undo"],
               "shuffle": ld["act_shuffle"], "magnet": ld["act_magnet"]}
        for i, f in enumerate(M["FEATS"]):
            row[f] = ld["x"][i]
        eval_rows.append(row)
    df_eval = pd.DataFrame(eval_rows)

    gbm_path = os.path.join(SKILL, "analysis", "heads_gbm.joblib")
    if gbm_heads:
        import joblib
        joblib.dump({"feats": M["FEATS"], "heads": gbm_heads,
                     "cohort": cohort_name, "sklearn": __import__("sklearn").__version__},
                    gbm_path, compress=3)
        log(f"Da ghi {len(gbm_heads)} dau GBM: {gbm_path}")
    elif os.path.exists(gbm_path):
        os.remove(gbm_path)          # khong con dau nao dung GBM -> bo file cu cho khoi lech
        log("Khong dau nao dung GBM -> da xoa heads_gbm.joblib cu")

    targets = [(MODEL_PATH, EVAL_PATH)]
    if also_root:
        targets.append((ROOT_MODEL_PATH, ROOT_EVAL_PATH))
    for mp, ep in targets:
        os.makedirs(os.path.dirname(mp), exist_ok=True)
        json.dump(M, open(mp, "w", encoding="utf-8"), indent=2)
        df_eval.to_csv(ep, index=False)
        log(f"Da ghi: {mp}")
        log(f"Da ghi: {ep}")

    log("HOAN TAT.", 100)
    return M


def _report(mae_old, mae_new, mae_cv, n_stage):
    print()
    print("=" * 74)
    print(f"  SO SANH MAE — truoc vs sau  (so level: early {n_stage['early']} / "
          f"mid {n_stage['mid']} / late {n_stage['late']})")
    print("=" * 74)
    print(f"  {'chi so':<13}{'giai doan':<8}{'truoc':>9}{'sau':>9}{'doi':>9}{'5-fold':>10}")
    print("-" * 74)
    for head, _, _ in HEADS_LIST:
        for s in STAGES:
            o = mae_old.get(head, {}).get(s)
            n = mae_new.get(head, {}).get(s)
            if n is None:
                continue
            d = f"{n - o:+.2f}" if o is not None else "  -"
            mark = ""
            if o is not None:
                mark = " ++" if n < o - 0.5 else (" --" if n > o + 0.5 else "")
            cv = mae_cv.get(head, {}).get(s)
            print(f"  {head:<13}{s:<8}{(f'{o:.2f}' if o is not None else '-'):>9}"
                  f"{n:>9.2f}{d:>9}{(f'{cv:.2f}' if cv is not None else '-'):>10}{mark}")
        print("-" * 74)
    print("  ++ = tot len ro ret (>0.5) · -- = te di ro ret · cot 5-fold = out-of-sample")
    print("=" * 74)
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Hieu chuan lai model winrate-target tu log tho.")
    ap.add_argument("csv_path", help="duong dan CSV log tho cua cohort")
    ap.add_argument("--cohort", default=None, help="ten cohort (ghi vao provenance)")
    ap.add_argument("--dry-run", action="store_true", help="khong ghi file, chi xem MAE")
    ap.add_argument("--also-write-root", action="store_true", help="ghi them ban sao ra <project>/analysis/")
    ap.add_argument("--no-cv", action="store_true", help="bo qua kiem dinh cheo 5-fold")
    ap.add_argument("--no-balance", action="store_true", help="KHONG can bang trong so theo giai doan")
    ap.add_argument("--no-gbm", action="store_true",
                    help="chi dung Ridge (bo lop phi tuyen Gradient Boosting)")
    a = ap.parse_args()
    run(a.csv_path, a.cohort, a.dry_run, a.also_write_root, not a.no_cv,
        not a.no_balance, not a.no_gbm)
