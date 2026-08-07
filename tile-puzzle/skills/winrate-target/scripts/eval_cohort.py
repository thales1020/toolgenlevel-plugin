# -*- coding: utf-8 -*-
"""
eval_cohort.py — do sai so cua MODEL DANG DUNG tren mot (hoac nhieu) cohort,
KHONG fit lai gi ca.

Khac recalibrate.py: script do HUAN LUYEN (thay doi model). Script nay chi CHAM DIEM
model hien tai tren du lieu that cua cohort khac -> biet model co TONG QUAT HOA duoc
sang tep nguoi choi khac hay chi khop rieng cohort no da hoc.

  - Cohort model da hoc  -> sai so "trong nha" (in-sample, lac quan)
  - Cohort khac          -> sai so THAT khi ap dung cho tep nguoi choi khac

CHAY:
  python scripts/eval_cohort.py <csv1> [<csv2> ...] [--names ten1,ten2,...]
  python scripts/eval_cohort.py ../../../data-v2/cohort_*.csv
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, SKILL)

import winrate_tool as W  # noqa: E402

CACHE_PATH = os.path.join(SKILL, "data", "cached_level_features.json")
STAGES = ["early", "mid", "late"]

# ten dau trong model  ->  ten cot ket qua that
HEADS = [
    ("att1",        "win_rate lan dau"),
    ("win_att",     "Win/Att %"),
    ("dur_win1",    "thoi luong (phut)"),
    ("revive_user", "revive %"),
    ("booster",     "booster %"),
    ("near_miss",   "near_miss %"),
    ("undo",        "undo %"),
    ("shuffle",     "shuffle %"),
    ("magnet",      "magnet %"),
]


def stage_of(L):
    return "early" if L <= 60 else ("mid" if L <= 140 else "late")


def actuals(csv_path):
    """Tinh 9 chi so THAT theo level — dung y het cong thuc trong recalibrate.py."""
    raw = pd.read_csv(csv_path)
    raw["u_undo"] = (raw["undo_used"] > 0).astype(int)
    raw["u_mag"] = (raw["magnet_used"] > 0).astype(int)
    raw["u_shuf"] = (raw["shuffle_used"] > 0).astype(int)
    raw["u_any"] = (raw.u_undo | raw.u_mag | raw.u_shuf).astype(int)

    first = raw[raw.attempt_num == 1]
    per_user = lambda c: raw.groupby(["level", "user_id"])[c].max().groupby("level").mean() * 100
    user_wins = raw[raw.result == "win"].groupby(["level", "user_id"])["attempt_num"].min()
    total_users = raw.groupby("level")["user_id"].nunique()

    return {
        "att1": first.groupby("level")["result"].apply(lambda s: (s == "win").mean() * 100),
        "win_att": raw.groupby("level")["result"].apply(lambda s: (s == "win").mean() * 100),
        "dur_win1": raw[raw.result == "win"].groupby("level")["duration_sec"].mean() / 60.0,
        "revive_user": per_user("revive"),
        "booster": per_user("u_any"),
        "near_miss": (user_wins[user_wins >= 3].groupby("level").size() / total_users * 100).fillna(0.0),
        "undo": per_user("u_undo"),
        "shuffle": per_user("u_shuf"),
        "magnet": per_user("u_mag"),
    }, total_users, raw


def evaluate(csv_path, cached):
    act, total_users, raw = actuals(csv_path)
    rows = []
    for lvl in sorted(total_users.index):
        if lvl not in cached or lvl not in act["att1"].index:
            continue
        x = np.array(cached[lvl]["x"], dtype=float)
        beta = cached[lvl]["beta"]
        st = stage_of(lvl)
        rec = {"level": lvl, "stage": st}
        for head, _ in HEADS:
            a = act[head].get(lvl)
            if a is None or (isinstance(a, float) and np.isnan(a)):
                continue
            # du bao tai DUNG vi tri level do (theta dong)
            rec[f"act_{head}"] = float(a)
            rec[f"pred_{head}"] = float(W._head(head, x, beta, lvl, st))
        rows.append(rec)
    df = pd.DataFrame(rows)
    return df, int(raw.user_id.nunique()), int(raw.shape[0])


def mae_table(df):
    out = {}
    for head, _ in HEADS:
        ac, pc = f"act_{head}", f"pred_{head}"
        if ac not in df.columns:
            continue
        out[head] = {}
        for st in STAGES:
            s = df[(df.stage == st) & df[ac].notna() & df[pc].notna()]
            if len(s) >= 3:
                out[head][st] = (float((s[ac] - s[pc]).abs().mean()), len(s))
    return out


def main(paths, names, quiet=False):
    cached = {it["level"]: it for it in json.load(open(CACHE_PATH, encoding="utf-8"))}
    prov = W.M.get("PROVENANCE", {})
    trained_on = prov.get("cohort", "(khong ro)")

    print("=" * 96)
    print(f"  CHAM DIEM MODEL HIEN TAI TREN NHIEU COHORT  —  model da hoc tu: {trained_on}")
    print(f"  (khong fit lai gi; cohort '{trained_on}' la 'trong nha', con lai la kiem dinh THAT)")
    print("=" * 96)

    results = {}
    for p, nm in zip(paths, names):
        if not os.path.exists(p):
            print(f"  [bo qua] khong thay {p}")
            continue
        df, nu, nr = evaluate(p, cached)
        results[nm] = (mae_table(df), nu, nr, len(df))
        tag = "  <== TRONG NHA" if nm == trained_on else ""
        print(f"  {nm:<16} {nr:>9,} luot | {nu:>7,} nguoi | {len(df):>4} level cham duoc{tag}")

    if not quiet:
        for head, label in HEADS:
            print()
            print(f"  {label}  (MAE — cang thap cang tot)")
            print(f"  {'cohort':<16}" + "".join(f"{s:>22}" for s in STAGES))
            print("  " + "-" * 82)
            for nm, (tbl, *_rest) in results.items():
                row = f"  {nm:<16}"
                for st in STAGES:
                    v = tbl.get(head, {}).get(st)
                    row += f"{(f'{v[0]:.2f}  (n={v[1]})' if v else '-'):>22}"
                row += "  <==" if nm == trained_on else ""
                print(row)
        print()
        print("=" * 96)
        print("  Doc bang: dong 'TRONG NHA' la cohort model da hoc -> luon dep hon.")
        print("  Chenh lech giua no va cac dong khac = MUC DO MODEL BI LE THUOC COHORT.")
        print("=" * 96)
    return results


MIN_N = 30          # o co mau nho hon thi la nhieu, khong tinh

# Nguong lech MAE coi la "troi". Hieu chuan tu do thuc te (2026-07-29, moc july_9_20):
#   cung build thang 7 : july_1_9 1.18 | bq_new 1.60 | july_20_22 3.00   -> KHONG nen bao
#   khac build (thang 6): june_1_21 8.55                                  -> PHAI bao
# Khoang trong that su nam giua 3.00 va 8.55 => chon 3.5. Nguong 2.0 truoc day bao nham
# ca july_20_22 (cung build) -> qua nhay, gay "canh bao ao" lam nguoi dung lo di canh bao that.
DRIFT_THRESHOLD = 3.5


def check_drift(results, trained_on, threshold=DRIFT_THRESHOLD):
    """So MAE cua tung cohort MOI voi cohort model da hoc. Tra ve (status, chi tiet).

    Chi xet o co n >= MIN_N. Bo qua chinh cohort da hoc (no la moc so sanh)."""
    home = results.get(trained_on, (None,))[0]
    if not home:
        return "UNKNOWN", {"reason": f"khong co cohort moc '{trained_on}' trong lan cham nay"}, []

    breaches, worst = [], 0.0
    per_cohort = {}
    for nm, (tbl, *_r) in results.items():
        if nm == trained_on:
            continue
        cohort_worst, cohort_breach = 0.0, []
        for head, _ in HEADS:
            for st in STAGES:
                h = home.get(head, {}).get(st)
                o = tbl.get(head, {}).get(st)
                if not h or not o or o[1] < MIN_N or h[1] < MIN_N:
                    continue
                d = o[0] - h[0]          # duong = cohort moi TE hon moc
                if d > cohort_worst:
                    cohort_worst = d
                if d > threshold:
                    cohort_breach.append((head, st, h[0], o[0], d))
        per_cohort[nm] = {"worst": round(cohort_worst, 2), "n_breach": len(cohort_breach)}
        breaches.extend([(nm, *b) for b in cohort_breach])
        worst = max(worst, cohort_worst)

    n_bad = sum(1 for v in per_cohort.values() if v["n_breach"] > 0)
    status = "WARN" if n_bad >= 2 or worst > 2 * threshold else ("OK" if not breaches else "WATCH")
    return status, {"worst_drift": round(worst, 2), "n_cohort_vuot": n_bad,
                    "tong_cohort_kiem": len(per_cohort), "threshold": threshold,
                    "per_cohort": per_cohort}, breaches


def print_drift_banner(status, info, breaches, trained_on):
    bar = "!" * 92 if status == "WARN" else "=" * 92
    print()
    print(bar)
    if status == "WARN":
        print("  [!!] CANH BAO TROI MODEL — NEN HIEU CHUAN LAI TRUOC KHI TIN KET QUA")
    elif status == "WATCH":
        print("  [~] CO DAU HIEU TROI NHE — theo doi, chua can hieu chuan lai")
    elif status == "OK":
        print("  [OK] MODEL CON DUNG — khong can hieu chuan lai")
    else:
        print("  [?] CHUA DU DU LIEU DE KET LUAN")
    print(bar)
    print(f"  Model moc          : {trained_on}")
    print(f"  Nguong canh bao    : lech > {info.get('threshold')} diem MAE")
    print(f"  Cohort da kiem     : {info.get('tong_cohort_kiem')}")
    print(f"  Cohort vuot nguong : {info.get('n_cohort_vuot')}")
    print(f"  Lech lon nhat      : {info.get('worst_drift')} diem")
    for nm, v in (info.get("per_cohort") or {}).items():
        flag = "  <-- vuot" if v["n_breach"] else ""
        print(f"    - {nm:<16} lech lon nhat {v['worst']:>6} diem | {v['n_breach']} o vuot{flag}")
    if breaches:
        print("\n  Chi tiet cac o vuot nguong (moc -> cohort moi):")
        for nm, head, st, hv, ov, d in sorted(breaches, key=lambda z: -z[5])[:12]:
            print(f"    {nm:<16}{head:<13}{st:<7}{hv:>7.2f} -> {ov:>6.2f}   (+{d:.2f})")
    if status == "WARN":
        print("\n  VIEC CAN LAM: python scripts/recalibrate.py <csv_cohort_moi> --cohort <ten> --dry-run")
        print("  Luu y: DUNG hieu chuan lai cho tung A/B test rieng le — se mat tinh so sanh")
        print("         giua cac test. Chi hieu chuan khi dan so THUC SU da doi (nhu bang tren).")
    print(bar)
    print()


def save_status(status, info, trained_on, names):
    from datetime import datetime, timezone
    path = os.path.join(SKILL, "analysis", "drift_status.json")
    json.dump({"status": status, "trained_on": trained_on,
               "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "cohorts_checked": names, **info},
              open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"  -> da ghi trang thai: {os.path.relpath(path, SKILL)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_paths", nargs="+")
    ap.add_argument("--names", default=None, help="ten cohort, phan cach bang dau phay")
    ap.add_argument("--check-drift", action="store_true",
                    help="so voi cohort moc, in CANH BAO va ghi analysis/drift_status.json")
    ap.add_argument("--threshold", type=float, default=DRIFT_THRESHOLD,
                    help=f"nguong lech MAE coi la troi (mac dinh {DRIFT_THRESHOLD})")
    ap.add_argument("--quiet", action="store_true", help="bo bang chi tiet, chi in ket luan troi")
    a = ap.parse_args()
    nms = (a.names.split(",") if a.names
           else [os.path.splitext(os.path.basename(p))[0].replace("cohort_", "") for p in a.csv_paths])
    res = main(a.csv_paths, nms, quiet=a.quiet)
    if a.check_drift:
        _t = W.M.get("PROVENANCE", {}).get("cohort", "(khong ro)")
        _st, _info, _br = check_drift(res, _t, a.threshold)
        print_drift_banner(_st, _info, _br, _t)
        save_status(_st, _info, _t, nms)
        sys.exit(1 if _st == "WARN" else 0)
