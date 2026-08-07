# -*- coding: utf-8 -*-
"""
winrate_tool.py — "Tao level voi layout [X] co chi so [Y]=[Z] o giai doan [early/mid/late]"

=========================== 9 CHI SO Y ===========================
KHONG chep so MAE vao day — tai lieu se lech ngay lan hieu chuan ke tiep (xem
ARCHITECTURE.md P8). Xem so SONG bang:

    python winrate_tool.py info        # in PROVENANCE + MAE in-sample/CV cua ca 9 dau

  win_rate (att1)  do kho, thang lan dau  <== DANG TIN NHAT, dung cai nay dat muc tieu
  thoi_luong       nhip game (phut)
  near_miss        co hoi IAP
  revive           ty le dung hoi sinh
  booster          ty le dung vat pham (tong)
  undo/shuffle/magnet   tach nho cua booster
  win_att          chi so PROMPT GOC — bi whale-cay lam ban, xem canh bao duoi

LUU Y: "booster/revive" la TY LE SU DUNG vat pham, KHONG phai doanh thu. Log khong
co cot mua hang (IAP) nao, nen tool khong du bao duoc tien.

CANH BAO — CAC COT KHONG DUNG DUOC (da kiem dinh split-half):
  Win/Att %      : do "whale cay may lan", KHONG do layout (corr o-nhiem/whale = +0.97).
                   Biet do kho hoan hao van chi cho MAE 7.6. Tran cung ~8.1. TRANH.
  Pass %, Dropout %, GiveUp %, AttWin avg, Revive Int % :
                   do tin cay noi tai < 0.5 — chia doi dan ra 2 ket qua khac nhau.
                   Khong model nao doan duoc. NEN GO khoi bang theo doi.

CAC KHOA CU trong winrate_model.json — KHONG dung:
  M["MAE"]      : bo MAE 5 chi so cua lan train GOC. Dung M["MAE_STAGE_CV"].
  M["OUTLIERS"] : danh sach cu, khong con khop tap fit hien tai.
  Khong script nao cap nhat 2 khoa nay (xem REFACTOR_PLAN 1.2).

=========================== CACH HOAT DONG ===========================
KHONG hoi quy thang win_rate. Dung MO HINH 3 TANG theo dung vat ly da chung minh:

   win_rate(layout @ vi tri) = E_dan[ sigmoid(theta_u - beta_layout) ]  +  du so
                                ^ DO tu 56K luot log    ^ doan tu layout

   Tang 1: beta = do kho noi tai cua layout (doan tu 36 feature, R2=0.56)
   Tang 2: ghep voi PHAN PHOI trinh do dan tai vi tri do
           -> E[sigmoid], KHONG phai sigmoid(trung binh) (sai lam Jensen: MAE vot len 16.4)
   Tang 3: hoc du so

=========================== 36 FEATURE ===========================
10 TINH (tu layout):
   intra_group, cover100, n_types, is_mystery, layerCount, tileCount, lpos
   dead_slot   : con thu 3 cua mot loai bi chon sau bao nhieu -> ket khay  (+ KHO)
   frac_3copy  : ty le tile thuoc loai co DUNG 3 con (bo ba tu dong)       (- DE)
   dead_slot_norm
   (dead_slot & frac_3copy tim ra tu playlog nguoi that — dead_slot la bien SO 1
    quyet dinh CA thoi luong (+1.35 phut) LAN revive% (+10.4 diem))

26 MO PHONG (cho BOT-NGUOI choi thu 20 lan x 3 muc ky nang):
   bprog_*   : bot don duoc BAO NHIEU % board truoc khi ket  <== bien then chot,
               thay cho "bot thang/thua" von BAO HOA 32-47% (bot thua sach, vo dung)
   bpeak_*, bmean_* : ap luc khay
   bforce_*  : ty le buoc bi ep (khong con nuoc tot)
   bwin_u2/u5/s1/u3s1 : BOT CHOI LAI VOI BOOSTER (undo/shuffle) — bot co thang duoc
               neu duoc cho booster khong? bwin_s1 la feature MO PHONG MANH NHAT:
               corr -0.63 voi revive_user%, -0.59 voi booster%, -0.58 voi do kho.

=========================== 16 LEVEL MODEL VAN SAI ===========================
early: L31 L38 L44 L58 L60 | mid: L64 L77 L86 L107 L114 L118 L119 L125 L133 L139
12/16 model doan DE HON thuc te. Chung KHONG khac biet ve mystery/dead_slot/tileCount
-> con mot loai "do kho bay" ma ca feature tinh lan bot deu chua nhin thay. CHUA GIAI THICH DUOC.
Bo 16 level nay ra: win_rate MAE 4.25 -> 3.54 (92% trong +-8).

CHAY:
   # PROMPT GOC: "tao level voi layout [X] co chi so [Y] la [Z] o giai doan [stage]"
   python winrate_tool.py gen win_att 70 mid --layout 54     # X=layout 54, Y=Win/Att, Z=70%
   python winrate_tool.py gen win_rate 87 late sym           # X=hinh doi xung sinh moi
   python winrate_tool.py target 70 mid win_att              # nguoc: can do kho beta bao nhieu
   python winrate_tool.py info
   (predict: import winrate_tool; winrate_tool.predict(board_json, engine_feats, level_pos))

gen_layout(metric, value, stage, symmetric=, base_layout=):
   base_layout=54 -> GIU nguyen hinh layout 54, chi gan lai quan/do kho.
   base_layout=None -> sinh hinh kim tu thap doi xung moi khop hinh hoc level that.
   Search CO PHAN HOI: engine gan quan -> forward-model do -> dich vung engine theo
   dau sai so -> lap. Bao "KHONG DAT" khi don bay bao hoa (vd: revive @ early).
"""
import sys, os, json

# ── Phai dat TRUOC moi import co the keo joblib/sklearn vao ──────────────────────────
# Cac dau GBM duoc unpickle tu joblib, va HistGradientBoosting.predict() goi
# sklearn._openmp_effective_n_threads() -> joblib.cpu_count(only_physical_cores=True)
# -> loky do so core VAT LY bang subprocess. Tren Windows 11 moi lenh do khong con ton
# tai, joblib IN THANG traceback "[WinError 2] The system cannot find the file specified"
# ra stderr o MOI lan chay `gen`.
#
# Da thu va KHONG du:
#   - LOKY_MAX_CPU_COUNT     -> chi gioi han so core, van goi duong do
#   - warnings.filterwarnings -> tat duoc dong UserWarning nhung traceback duoc in
#                                TRUC TIEP ra stderr, khong qua co che warnings
# Cai hieu qua: dat OMP_NUM_THREADS -> sklearn tra ve ngay, khong hoi so core vat ly.
# Dat = 1 vi ta du bao TUNG DONG mot; nhieu thread chi them chi phi dieu phoi.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))

import numpy as np
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
M = json.load(open(os.path.join(HERE, "analysis", "winrate_model.json"), encoding="utf-8"))
W_POLICY = np.array(M["HUMAN_POLICY"])
ENGINE_KEYS = ["intra_group", "cover100", "n_types", "is_mystery", "layerCount", "tileCount"]
BOT_TEMPS = [0.15, 0.5, 0.8]
BOT_RUNS = 20
HEAD_ALIAS = {"win_rate": "att1", "thoi_luong": "dur_win1", "revive": "revive_user", "booster": "booster",
              "undo": "undo", "shuffle": "shuffle", "magnet": "magnet"}


# --------------------------------------------------------------------------- bot
def _build(sj):
    T = []
    for ly in sorted(sj["layers"], key=lambda l: l["index"]):
        for s in ly["stones"]:
            i = int(s.get("i", 0))
            T.append((float(s["x"]), float(s["y"]), ly["index"], i,
                      (i if i >= 1001 else 0), float(s.get("s", 0) or 0)))
    n = len(T)
    def hf(t):
        sp = t[4]
        if not sp: return 0.5
        if sp == 1001: return 1.5 if t[5] >= 1.15 else 1.0
        return 1.5 if t[5] >= 0.85 else 1.0
    AB = [[] for _ in range(n)]; BL = [[] for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j: continue
            h = hf(T[i]) + hf(T[j])
            if abs(T[i][0]-T[j][0]) < h and abs(T[i][1]-T[j][1]) < h:
                if T[j][2] > T[i][2]: AB[i].append(j)
                elif T[j][2] < T[i][2]: BL[i].append(j)
    return T, AB, BL


def _play(T, AB, BL, seed, temp, n_undo=0, n_shuffle=0):
    """BOT-NGUOI (chinh sach gap hoc tu playlog that). Tra ve CACH CHOI, khong chi thang/thua."""
    rng = np.random.default_rng(seed); n = len(T)
    typ = [t[3] for t in T]; spec = [t[4] for t in T]; lay = [t[2] for t in T]
    blocked = [len(AB[i]) for i in range(n)]
    alive = [True]*n; n_alive = n
    remain = Counter(); pickable_t = Counter()

    def rm(i):
        nonlocal n_alive
        alive[i] = False; n_alive -= 1
        if not spec[i]:
            remain[typ[i]] -= 1
            if blocked[i] == 0: pickable_t[typ[i]] -= 1
        for j in BL[i]:
            if alive[j]:
                blocked[j] -= 1
                if blocked[j] == 0 and not spec[j]: pickable_t[typ[j]] += 1

    for i in range(n):
        if not spec[i]:
            remain[typ[i]] += 1
            if blocked[i] == 0: pickable_t[typ[i]] += 1

    def autoclear():
        ch = True
        while ch:
            ch = False
            for i in range(n):
                if alive[i] and spec[i] and blocked[i] == 0: rm(i); ch = True

    autoclear()
    tray = []; hist = []; trays = []; forced = 0; used_u = 0; used_s = 0; steps = 0
    while n_alive > 0:
        steps += 1
        if steps > n*3: break
        cands = [i for i in range(n) if alive[i] and not spec[i] and blocked[i] == 0]
        if not cands: break
        c = Counter(tray); ts = len(tray); F = []
        # DA THU va BO: chan cung nuoc "thua chac" khi khay>=6 (chi cho nuoc hoan thanh
        # bo 3). KHONG hieu qua — do tren 120 level: thang 39.7%->39.6%, corr voi nguoi
        # that 0.354->0.316 (te hon). Ly do: 57.5% luot o trang thai khay>=6 VAN con
        # nuoc an toan, va W_POLICY da uu tien nuoc do rat manh (+3.37) nen bot von da
        # gan nhu luon chon dung -> loc them la thua. 42.5% con lai thi da het duong tu
        # nhieu buoc TRUOC. Ket luan: sai lam cua bot khong o nuoc cuoi ma o viec THIEU
        # NHIN TRUOC — muon sua phai them beam search, xem REFACTOR_PLAN Phase 3.3.
        for i in cands:
            k = typ[i]
            ub = sum(1 for j in BL[i] if alive[j] and blocked[j] == 1)
            isnew = 1.0 if c[k] == 0 else 0.0
            F.append([1.0 if c[k]==2 else 0.0, 1.0 if c[k]==1 else 0.0, isnew,
                      isnew*ts, pickable_t[k]/3.0, remain[k]/6.0, lay[i]/10.0, ub/3.0])
        if all(c[typ[i]] == 0 for i in cands) and ts >= 4: forced += 1
        s = np.array(F) @ W_POLICY / temp; s -= s.max()
        p = np.exp(s); p /= p.sum()
        i = cands[rng.choice(len(cands), p=p)]
        rm(i); tray.append(typ[i]); hist.append(i)
        cc = Counter(tray)
        for k in list(cc):
            while cc[k] >= 3:
                for _ in range(3): tray.remove(k)
                cc[k] -= 3
        autoclear()
        trays.append(len(tray))
        if len(tray) >= 7:
            if used_u < n_undo and hist:                      # BOOSTER: undo
                j = hist.pop(); tray.pop()
                alive[j] = True; n_alive += 1
                if not spec[j]:
                    remain[typ[j]] += 1
                    if blocked[j] == 0: pickable_t[typ[j]] += 1
                for q in BL[j]:
                    if alive[q]:
                        blocked[q] += 1
                        if blocked[q] == 1 and not spec[q]: pickable_t[typ[q]] -= 1
                used_u += 1; continue
            if used_s < n_shuffle:                            # BOOSTER: shuffle
                ids = [x for x in range(n) if alive[x] and not spec[x]]
                ks = [typ[x] for x in ids]; rng.shuffle(ks)
                pickable_t.clear()
                for x, k in zip(ids, ks):
                    typ[x] = k
                    if blocked[x] == 0: pickable_t[k] += 1
                used_s += 1; continue
            break
    return dict(won=1 if n_alive == 0 else 0, progress=1-n_alive/n,
                peak_tray=max(trays) if trays else 0,
                mean_tray=float(np.mean(trays)) if trays else 0.0,
                forced=forced/max(steps, 1))


# --------------------------------------------------------------------- features
def features(sj, engine_feats, level_pos):
    bt = defaultdict(list); nlay = len(sj["layers"]); nt = 0
    for ly in sj["layers"]:
        for s in ly["stones"]:
            i = int(s.get("i", -1))
            if i >= 1001: continue
            bt[i].append(ly["index"]); nt += 1
    trap = []
    for ls in bt.values():
        ls = sorted(ls, reverse=True)
        if len(ls) >= 3: trap.append(ls[1] - ls[-1])
    ds = float(np.mean(trap)) if trap else 0.0
    cnt = Counter({k: len(v) for k, v in bt.items()})
    f = {k: float(engine_feats[k]) for k in ENGINE_KEYS}
    f["dead_slot"] = ds
    f["dead_slot_norm"] = ds / max(nlay, 1)
    f["frac_3copy"] = sum(v for v in cnt.values() if v == 3) / max(nt, 1)
    f["lpos"] = float(np.log(max(level_pos, 1)))

    T, AB, BL = _build(sj)
    for tp in BOT_TEMPS:
        R = [_play(T, AB, BL, 977*k + int(tp*1000), tp) for k in range(BOT_RUNS)]
        f[f"bwin_{tp}"]     = np.mean([r["won"] for r in R])
        f[f"bprog_{tp}"]    = np.mean([r["progress"] for r in R])
        f[f"bprogmax_{tp}"] = np.max([r["progress"] for r in R])
        f[f"bpeak_{tp}"]    = np.mean([r["peak_tray"] for r in R])
        f[f"bmean_{tp}"]    = np.mean([r["mean_tray"] for r in R])
        f[f"bforce_{tp}"]   = np.mean([r["forced"] for r in R])
    for nu, ns, tag in [(2, 0, "u2"), (5, 0, "u5"), (0, 1, "s1"), (3, 1, "u3s1")]:
        R = [_play(T, AB, BL, 555*k, 0.5, n_undo=nu, n_shuffle=ns) for k in range(BOT_RUNS)]
        f[f"bwin_{tag}"]  = np.mean([r["won"] for r in R])
        f[f"bundo_{tag}"] = 0.0                      # giu cho khop schema; khong dung
    return f


# ------------------------------------------------------------------------ model
def _stage(L): return "early" if L <= 60 else ("mid" if L <= 140 else "late")


def _theta(theta_kind, lvl, stage):
    """Du bao phan phoi theta tai level 'lvl' dua tren phieu song sot Reach.
       Dung inverse Mills ratio de sua select-bias tu log thinh.
    """
    try:
        from scipy.stats import norm
        sm = M.get("SURVIVAL_MODEL", {
            "reach_a": 0.027942,
            "reach_b": 2.6352,
            "att1": {
                "intercept": -0.2733,
                "coef_lvl": 0.0015,
                "coef_mills": 0.3312
            },
            "all": {
                "intercept": -1.1712,
                "coef_lvl": 0.0015,
                "coef_mills": 0.4921
            }
        })
        
        # 1. Reach rate decay
        a, b = sm["reach_a"], sm["reach_b"]
        reach_rate = 1.0 / ((1.0 + a * lvl) ** b)
        
        # 2. Mills ratio
        z_cut = norm.ppf(1.0 - max(min(reach_rate, 0.9999), 0.0001))
        mills_ratio = norm.pdf(z_cut) / max(reach_rate, 0.0001)
        
        # 3. Predict mean and std of theta based on the reach funnel
        params = sm[theta_kind]
        mu = params["intercept"] + params["coef_lvl"] * lvl + params["coef_mills"] * mills_ratio
        
        if theta_kind == "att1":
            std = max(-0.001776 * lvl + 1.603511, 0.1)
        else:
            std = max(-0.002056 * lvl + 1.859607, 0.1)
            
        # 4. Generate deterministic standard normal samples (size 1000)
        rng = np.random.default_rng(42)
        std_normal = rng.normal(0.0, 1.0, 1000)
        
        return mu + std * std_normal
    except Exception:
        # Fallback to stage theta if anything fails
        t = M["THETA"][theta_kind]
        return np.array(t["level"].get(str(int(lvl))) or t["stage"][stage])


def _beta(x):
    z = (x - np.array(M["s1_mean"])) / np.array(M["s1_scale"])
    return float(z @ np.array(M["r1_coef"]) + M["r1_int"])


def _inv(level_pos):
    """Vector TON KHO (booster/vi tien trung binh cua dan so) tai vi tri level do.

    Nguoi choi chi dung booster khi HO CO booster — day la thong tin kinh te ma cac
    dau linear can. Bang duoc pipeline ghi vao M["INVENTORY"]; level nam ngoai bang
    thi lay level gan nhat (chan hai dau) thay vi ngoai suy."""
    inv = M.get("INVENTORY")
    if not inv:
        return []
    tbl = inv["by_level"]
    key = str(int(level_pos))
    if key in tbl:
        return tbl[key]
    lv = sorted(int(k) for k in tbl)
    nearest = min(lv, key=lambda L: abs(L - level_pos))
    return tbl[str(nearest)]


_GBM = None            # cache cac dau phi tuyen (nap tre, chi khi co file)
_GBM_TRIED = False


def _gbm():
    """Nap cac dau GRADIENT BOOSTING (neu co). Tra {} khi khong co / nap loi.

    Vi sao co ca hai lop: quan he layout->hanh vi la PHI TUYEN — do duoc: boosting thang
    Ridge 18/21 o, tong -11.88 diem MAE (kiem dinh cheo). Nhung boosting phai luu bang
    joblib (nhi phan, phu thuoc phien ban sklearn) nen KHONG soi duoc he so bang mat.
    Giai phap: GIU CA HAI — boosting lam lop chinh, Ridge trong JSON lam DU PHONG. Neu
    file joblib thieu/khong tuong thich, tool tu rot ve Ridge chu khong chet."""
    global _GBM, _GBM_TRIED
    if _GBM_TRIED:
        return _GBM or {}
    _GBM_TRIED = True
    p = os.path.join(HERE, "analysis", "heads_gbm.joblib")
    if not os.path.isfile(p):
        return {}
    try:
        # Tren Windows, joblib/loky do so core bang subprocess -> that bai va in mot khoi
        # UserWarning + traceback lam ban output CLI moi lan chay. Dat san bien nay de tat.
        os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 4))
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import joblib
        obj = joblib.load(p)
        if obj.get("feats") != M["FEATS"]:          # model va GBM lech tap feature
            print("[!] heads_gbm.joblib lech FEATS so voi winrate_model.json -> bo qua, dung Ridge")
            return {}
        _GBM = obj.get("heads", {})
    except Exception as e:
        print(f"[!] Khong nap duoc heads_gbm.joblib ({type(e).__name__}) -> dung Ridge du phong")
        _GBM = {}
    return _GBM or {}


def _head(name, x, beta, level_pos, stage):
    h = M["HEADS"][name]
    if h["kind"] == "sigmoid":
        th = _theta(h["theta_kind"], level_pos, stage)
        p = float(np.mean(1/(1+np.exp(-(M["B0"] + th - beta)))))      # tang 2: E[sigmoid]
        p = min(max(p, 0.02), 0.98); off = np.log(p/(1-p))
        feat = np.concatenate([x, [beta, off]])
        g = _gbm().get(name)
        if g is not None:                                            # tang 3 phi tuyen
            return 100/(1+np.exp(-(off + float(g.predict(feat.reshape(1, -1))[0]))))
        z = (feat - np.array(h["mean"])) / np.array(h["scale"])
        return 100/(1+np.exp(-(off + float(z @ np.array(h["coef"]) + h["int"]))))  # tang 3
    tail = [beta] + (list(_inv(level_pos)) if h.get("uses_inv") else [])
    feat = np.concatenate([x, tail])
    g = _gbm().get(name)
    if g is not None:
        return float(g.predict(feat.reshape(1, -1))[0])
    z = (feat - np.array(h["mean"])) / np.array(h["scale"])
    return float(z @ np.array(h["coef"]) + h["int"])


def predict(sj, engine_feats, level_pos):
    """9 chi so du bao cho layout dat tai vi tri level_pos.
       win_att_pct = win_rate_per_att (Win/Att %) — chi so cua PROMPT GOC. Sai so lon hon
       (+-9) vi bi drop + user cay lai lam ban; win_rate_dot1 dang tin cay hon (+-4).
       undo/shuffle/magnet_pct: ti le user dung tung loai booster rieng biet."""
    f = features(sj, engine_feats, level_pos)
    x = np.array([f[k] for k in M["FEATS"]], dtype=float)
    beta = _beta(x); st = _stage(level_pos)
    # Sai so bao ra ngoai: uu tien MAE KIEM DINH CHEO (out-of-sample, trung thuc hon
    # in-sample). Lam tron 2 chu so — truoc day in ca 15 chu so thap phan.
    _cv = M.get("MAE_STAGE_CV") or {}
    _is = M["MAE_STAGE"]
    e = {k: {s: round(float(_cv.get(k, {}).get(s, _is.get(k, {}).get(s, 5.0))), 2)
             for s in ("early", "mid", "late")} for k in _is}
    # Kiem tra xem model da co 3 head moi chua (backward compat)
    has_booster_split = "undo" in M.get("HEADS", {})
    out = dict(
        beta=round(beta, 3), stage=st,
        win_att_pct      =round(_head("win_att",     x, beta, level_pos, st), 1),
        win_rate_dot1_pct=round(_head("att1",        x, beta, level_pos, st), 1),
        thoi_luong_phut  =round(_head("dur_win1",    x, beta, level_pos, st), 2),
        revive_user_pct  =round(_head("revive_user", x, beta, level_pos, st), 1),
        booster_pct      =round(_head("booster",     x, beta, level_pos, st), 1),
        near_miss_pct    =round(_head("near_miss",   x, beta, level_pos, st), 1),
        sai_so=dict(win_att=e["win_att"][st], win_rate=e["att1"][st], thoi_luong=e["dur_win1"][st],
                    revive=e["revive_user"][st], booster=e["booster"][st],
                    near_miss=e.get("near_miss", {}).get(st, 5.0),
                    undo=e.get("undo", {}).get(st, 5.0),
                    shuffle=e.get("shuffle", {}).get(st, 5.0),
                    magnet=e.get("magnet", {}).get(st, 5.0)),
        features=f)
    if has_booster_split:
        out["undo_pct"]    = round(_head("undo",    x, beta, level_pos, st), 1)
        out["shuffle_pct"] = round(_head("shuffle", x, beta, level_pos, st), 1)
        out["magnet_pct"]  = round(_head("magnet",  x, beta, level_pos, st), 1)
    return out


def required_difficulty(target_pct, stage, metric="win_rate", level_pos=None):
    """NGUOC: muon chi so = Z% o giai doan nay -> layout can beta bao nhieu.
       metric='win_rate' (choi lan dau, theta att1) hoac 'win_att' (moi luot, theta all).
       level_pos: vi tri man cu the (dung theta DONG theo phieu song sot, giong predict()/
       gen()). None -> dung vi tri dai dien cua stage (_STAGE_POS), VAN la theta dong,
       khong con roi ve theta TINH theo stage nhu truoc (dong bo voi predict/gen)."""
    kind = "all" if metric in ("win_att", "win_rate_per_att") else "att1"
    pos = level_pos if level_pos is not None else _STAGE_POS[stage]
    th = _theta(kind, pos, stage)
    lo, hi = -8.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        p = np.mean(1/(1+np.exp(-(M["B0"] + th - mid)))) * 100
        if p > target_pct: lo = mid
        else: hi = mid
    return (lo + hi) / 2


# =========================================================================== #
#  GEN LAYOUT — sinh layout dat chi so muc tieu (search CO PHAN HOI)          #
# =========================================================================== #
# Metric | cot CSV     | key predict          | sign = huong theo do kho
#   win_rate  : cang KHO cang GIAM  -> sign -1
#   thoi_luong/revive/booster : cang KHO cang TANG -> sign +1
_METRIC = {
    "win_att":   dict(col="win_att",     out="win_att_pct",       sign=-1, tol=6.0,  unit="%"),
    "win_rate":  dict(col="att1",        out="win_rate_dot1_pct", sign=-1, tol=5.0,  unit="%"),
    "thoi_luong":dict(col="dur_win1",    out="thoi_luong_phut",   sign=+1, tol=0.6,  unit="phut"),
    "revive":    dict(col="revive_user", out="revive_user_pct",   sign=+1, tol=5.0,  unit="%"),
    "booster":   dict(col="booster",     out="booster_pct",       sign=+1, tol=6.0,  unit="%"),
    "near_miss": dict(col="near_miss_rate_pct", out="near_miss_pct", sign=+1, tol=5.0, unit="%"),
    "undo":      dict(col="undo",        out="undo_pct",          sign=+1, tol=5.0,  unit="%"),
    "shuffle":   dict(col="shuffle",     out="shuffle_pct",       sign=+1, tol=5.0,  unit="%"),
    "magnet":    dict(col="magnet",      out="magnet_pct",        sign=+1, tol=5.0,  unit="%"),
}
_STAGE_POS = {"early": 30, "mid": 100, "late": 180}


def _profile(metric, value, stage):
    """Ho so tu LEVEL THAT gan muc tieu: hinh hoc trung tam + vung engine + bien (chong ngoai suy)."""
    import pandas as pd
    m = pd.read_csv(os.path.join(HERE, "analysis", "final_eval_4Y.csv"))
    cfg = _METRIC[metric]; col = cfg["col"]
    near = m[(m.stage == stage) & (m[col].sub(value).abs() <= cfg["tol"])]
    if len(near) < 4:                                   # noi long neu qua it
        near = m[(m.stage == stage) & (m[col].sub(value).abs() <= 2*cfg["tol"])]
    if len(near) < 4:
        near = m[m[col].sub(value).abs() <= 2*cfg["tol"]]
    wide = m[(m.stage == stage) & (m[col].sub(value).abs() <= 2*cfg["tol"])]
    if len(wide) < 6: wide = near
    # QUAN TRONG: phai co ca feature BOT. Thieu chung -> model ngoai suy ma khong ai biet
    # (vd: board doi xung co bprog=0.20 trong khi moi level that o Win/Att 82% deu >=0.25).
    gk = ["layerCount", "tileCount", "n_types", "intra_group", "cover100", "dead_slot",
          "bprog_0.15", "bprog_0.5", "bprog_0.8"]
    return dict(
        n=len(near),
        center={k: float(near[k].median()) for k in gk},
        bounds={k: (float(wide[k].min()), float(wide[k].max())) for k in gk},
        target_metric_mean=float(near[col].mean()))


def _sym_pyramids(target_layers, target_tiles):
    """Kim tu thap DOI XUNG (luoi can giua). NOI SUY tuyen tinh day->dinh de dat DUNG so lop
    ma khong bi phinh so quan (constant-shrink khong lam duoc 7 lop x 105 quan)."""
    nlay = max(3, int(round(target_layers))); tiles_t = int(round(target_tiles))
    win = max(18, int(0.25*tiles_t))
    out = []
    for bw in range(3, 10):
        for bh in range(3, 10):
            for aw in (1, 2, 3):
                for ah in (1, 2):
                    if aw > bw or ah > bh: continue
                    if not (0.6 <= bw/bh <= 1.7): continue        # CHAT LUONG HINH: khong lay dai hep
                    sizes = []
                    for L in range(nlay):
                        fr = L/(nlay-1) if nlay > 1 else 0.0
                        nx = max(1, int(round(bw + fr*(aw-bw))))
                        ny = max(1, int(round(bh + fr*(ah-bh))))
                        sizes.append((nx, ny))
                    tot = sum(nx*ny for nx, ny in sizes)
                    if tot % 3 != 0: continue
                    if abs(tot - tiles_t) > win: continue
                    # bat buoc thu nho dan (khong co lop to hon lop duoi)
                    if any(sizes[i][0]*sizes[i][1] > sizes[i-1][0]*sizes[i-1][1] for i in range(1, nlay)):
                        continue
                    # kim tu thap THAT: phai co it nhat 3 buoc thu nho thuc su
                    if sum(1 for i in range(1, nlay)
                           if sizes[i][0]*sizes[i][1] < sizes[i-1][0]*sizes[i-1][1]) < 3: continue
                    # uu tien hinh CAN DOI: phat neu day qua det
                    pen = abs(bw/bh - 1.0)
                    out.append((abs(tot-tiles_t) + 6*pen, sizes, tot))
    out.sort(key=lambda z: z[0])
    seen = set(); uniq = []
    for _, sizes, tot in out:
        key = tuple(sizes)
        if key in seen: continue
        seen.add(key); uniq.append((sizes, tot))
    return uniq[:4]


def _shape_to_cells(sizes):
    return [{"cells": [{"x": float(i-(nx-1)/2), "y": float(j-(ny-1)/2)}
                       for i in range(nx) for j in range(ny)]} for (nx, ny) in sizes]


def _board_to_slots(bd):
    return {"layers": [{"index": ly["id"],
                        "stones": [{"x": c["x"], "y": c["y"], "i": int(c["tile_id"])}
                                   for c in ly["cells"] if c["tile_id"] >= 0]}
                       for ly in bd["layers"]]}


def _sym_pct(sj):
    ok = tot = 0
    for ly in sj["layers"]:
        S = {(round(s["x"], 3), round(s["y"], 3)) for s in ly["stones"]}
        for (x, y) in S:
            tot += 1
            if (round(-x, 3), y) in S and (x, round(-y, 3)) in S: ok += 1
    return ok/max(tot, 1)


def _load_layout_cells(layout_id):
    """Doc HINH (chi toa do x,y theo lop) cua mot layout co san tu Note - Layout.csv."""
    import csv as _csv
    _csv.field_size_limit(10**7)
    lid = f"L{int(layout_id)}"
    with open(os.path.join(HERE, "Note - Layout.csv"), encoding="utf-8") as fh:
        for r in _csv.DictReader(fh):
            if (r.get("layoutId") or "").strip() == lid:
                sj = json.loads(r["slotsJson"]); layers = []
                for ly in sorted(sj["layers"], key=lambda l: l["index"]):
                    cells = [{"x": float(s["x"]), "y": float(s["y"])} for s in ly["stones"]]
                    if cells: layers.append({"cells": cells})
                return layers
    raise ValueError(f"khong tim thay layout {layout_id} trong Note - Layout.csv")


def gen_layout(target_metric="win_rate", target_value=87.0, stage="late",
               symmetric=False, base_layout=None, samples=3, rounds=4, verbose=True):
    """Sinh/tinh-chinh layout dat chi so muc tieu bang SEARCH CO PHAN HOI (khong random mu).

    - base_layout=None : sinh HINH MOI (kim tu thap doi xung) khop hinh hoc level that.
    - base_layout=54   : GIU HINH cua layout 54 co san, chi gan lai quan/do kho (dung cho PROMPT GOC).
    Vong lap: engine gan quan trong vung dich -> forward-model do -> DICH vung engine theo dau
    sai so -> lap. Chi nhan ket qua NAM TRONG phan bo du lieu that (chong ngoai suy).
    """
    import sys as _sys
    # Tim engine cua skill gen-layout: uu tien layout PLUGIN (../gen-layout/engine),
    # roi den layout DEV (toolgenlevel-plugin/...). Lay cai nao ton tai.
    _cands = [
        os.path.join(HERE, "..", "gen-layout", "engine"),                                  # trong plugin
        os.path.join(HERE, "toolgenlevel-plugin", "tile-puzzle", "skills", "gen-layout", "engine"),  # dev
    ]
    eng = next((os.path.abspath(p) for p in _cands if os.path.isdir(p)), os.path.abspath(_cands[0]))
    if eng not in _sys.path: _sys.path.insert(0, eng)
    from tile_api import api_create_board, api_auto_generate

    cfg = _METRIC[target_metric]; pos = _STAGE_POS[stage]
    prof = _profile(target_metric, target_value, stage)
    C = prof["center"]; B = prof["bounds"]
    ratio = (C["cover100"]/C["intra_group"]) if C["intra_group"] > 1 else 1.6
    intra_c = max(C["intra_group"], 4.0)                # tam vung engine ban dau

    # ── CHON NUT DIEU KHIEN THEO SUC MANH THAT (do tu M["r1_coef"]) ──────────────
    # LOI CU: vong phan hoi chi xoay `intra_group`. Nhung trong so cua intra_group len
    # beta chi la -0.0036 (hang 33/36) — gan nhu KHONG NOI VAO DAU, va con SAI CHIEU so
    # voi gia dinh cua code cu. Do la ly do `gen booster 17 early` day intra tu 7 len 55
    # (kich tran) ma du bao khong nhuc nhich (3.4% -> 3.6%), roi bo cuoc lech 7.8 diem.
    # Cac nut engine dieu khien duoc, xep theo |coef| len beta:
    #     layerCount  -0.567  (hang 2/36)  <- MANH NHAT, gap ~142 lan intra_group
    #     n_types     +0.144  (hang 17/36)
    #     cover100    -0.054
    #     tileCount   -0.025
    #     intra_group -0.004  (hang 33/36)
    # => xoay layerCount + n_types. DAU quan trong: layerCount AM (them lop = DE hon),
    #    n_types DUONG (them mau = KHO hon).
    _r1 = dict(zip(M["FEATS"], M["r1_coef"]))
    _w_layer = _r1.get("layerCount", -0.57)
    _w_types = _r1.get("n_types", 0.14)
    layer_c = float(C["layerCount"])                    # tam so LOP
    ntype_c = float(C["n_types"])                       # tam so MAU

    def _mk_shapes(lc):
        """Sinh lai danh sach hinh theo so lop muc tieu, ep trong bien chong-ngoai-suy."""
        lo, hi = B["layerCount"]
        lc = float(np.clip(lc, lo, hi))
        return [(_shape_to_cells(sz), tot, f"pyramid{list(sz)}")
                for sz, tot in _sym_pyramids(lc, C["tileCount"])], lc

    def _mk_colors(nc):
        lo, hi = B["n_types"]
        nc = float(np.clip(nc, max(lo, 4), hi))
        return sorted({int(np.clip(round(nc)+d, max(lo, 4), hi)) for d in (-1, 0, 1)}), nc

    if base_layout is not None:                          # GIU HINH layout co san
        cells0 = _load_layout_cells(base_layout)
        tot0 = sum(len(l["cells"]) for l in cells0)
        shapes = [(cells0, tot0, f"layout {base_layout}")]
        # hinh co dinh -> khong chan tileCount/layerCount, nhung VAN chan feature bot
        geo_keys = ("intra_group", "cover100", "dead_slot",
                    "bprog_0.15", "bprog_0.5", "bprog_0.8")
    else:                                                # SINH HINH moi
        shapes, layer_c = _mk_shapes(layer_c)
        geo_keys = ("intra_group", "cover100", "n_types", "tileCount", "layerCount", "dead_slot",
                    "bprog_0.15", "bprog_0.5", "bprog_0.8")
    colors, ntype_c = _mk_colors(ntype_c)

    def in_dist(ef, f):
        for k in geo_keys:
            v = ef.get(k, f.get(k)); lo, hi = B[k]
            if not (lo-1e-6 <= v <= hi+1e-6): return False
        return True

    if verbose:
        print(f"[gen_layout] muc tieu {target_metric}={target_value}{cfg['unit']} @ {stage} (pos {pos})")
        src = f"GIU hinh {shapes[0][2]} ({int(shapes[0][1])} quan)" if base_layout is not None \
              else f"{len(shapes)} hinh doi xung moi"
        print(f"  ho so tu {prof['n']} level that: intra~{C['intra_group']:.0f} cover~{C['cover100']:.0f} "
              f"n_types~{C['n_types']:.0f} | {src} x {colors} mau, {rounds} vong phan hoi\n")

    best = None                                          # (err, out, sj, ef, meta)
    for rd in range(rounds):
        preds = []
        lo_i, hi_i = max(2, intra_c-6), intra_c+6
        lo_c, hi_c = max(2, intra_c*ratio-8), intra_c*ratio+8
        for cells, tot, label in shapes:
            for cc in colors:
                for s in range(samples):
                    bd = api_create_board(f"gl_{rd}_{cc}_{s}", cells)
                    try:
                        r = api_auto_generate(bd, params={
                                "level_number": pos, "color_count": cc, "style_mode": 3,
                                "extended": True, "validate": True},
                            target={"intra_min": lo_i, "intra_max": hi_i,
                                    "cover_min": lo_c, "cover_max": hi_c}, max_attempts=40)
                    except Exception:
                        continue
                    if not r.get("board"): continue
                    sj = _board_to_slots(r["board"])
                    if symmetric and _sym_pct(sj) < 0.999: continue
                    types = {st_["i"] for l in sj["layers"] for st_ in l["stones"] if st_["i"] < 1001}
                    ef = dict(intra_group=float(r["score"].get("intra_group", 0)),
                              cover100=float(r["score"].get("cover100", 0)),
                              n_types=float(len(types)), is_mystery=0.0,
                              layerCount=float(len(sj["layers"])),
                              tileCount=float(sum(len(l["stones"]) for l in sj["layers"])))
                    try: out = predict(sj, ef, pos)
                    except Exception: continue
                    pv = out[cfg["out"]]; err = abs(pv - target_value)
                    ind = in_dist(ef, out["features"])
                    preds.append((pv, ind))
                    cand = (err, out, sj, ef, dict(label=label, cc=cc, in_dist=ind,
                                                   sym=_sym_pct(sj), round=rd))
                    # uu tien: TRONG phan bo truoc, roi toi sai so nho
                    if best is None or (ind, -err) > (best[4]["in_dist"], -best[0]):
                        best = cand
        if not preds:
            # Engine khong sinh duoc ung vien nao (hinh moi bat kha thi, hoac bo loc doi xung
            # loai het). Truoc day nhanh nay IM LANG -> nhin ben ngoai tuong search da dung
            # som. Nay bao ro va NOI LONG dan thay vi chi day intra.
            if verbose:
                print(f"  vong {rd}: lop={layer_c:.1f} mau={ntype_c:.1f} -> engine khong sinh duoc "
                      f"ung vien nao, noi long va thu lai")
            intra_c = float(np.clip(intra_c + 4, 2.0, 55.0))
            if base_layout is None:                       # lui so lop ve giua vung cho phep
                lo_l, hi_l = B["layerCount"]
                layer_c = float(np.clip((layer_c + (lo_l + hi_l) / 2) / 2, lo_l, hi_l))
                shapes, layer_c = _mk_shapes(layer_c)
            continue
        # PHAN HOI lay MEDIAN cua cac mau TRONG VUNG (mean cua tat ca bi hinh xau keo lech)
        ind_p = [p for p, i in preds if i]
        ref = float(np.median(ind_p)) if ind_p else float(np.median([p for p, _ in preds]))
        err = target_value - ref
        if verbose:
            print(f"  vong {rd}: lop={layer_c:.1f} mau={ntype_c:.1f} intra={intra_c:.1f} | "
                  f"pred median(trong-vung)={ref:.1f}{cfg['unit']} ({len(ind_p)}/{len(preds)} mau) | "
                  f"sai so={err:+.1f} | best_lech={best[0]:.1f}")
        if abs(err) < 0.5*cfg["tol"] and best[4]["in_dist"]: break

        # ── PHAN HOI: xoay cac nut THUC SU noi vao beta ──────────────────────────
        # push > 0  ==>  can lam KHO hon (de dat muc tieu)
        push = cfg["sign"] * err / max(cfg["tol"], 1e-6)     # chuan hoa theo dung sai
        push = float(np.clip(push, -3.0, 3.0))

        # beta doi mot luong  w * delta_feature  -> muon beta TANG (kho hon) thi delta phai
        # CUNG DAU voi w. Nen: delta = sign(w) * push.
        #   layerCount w<0  -> bot lop  |  n_types w>0 -> them mau
        new_layer = layer_c + (1.0 if _w_layer > 0 else -1.0) * push
        new_ntype = ntype_c + (1.0 if _w_types > 0 else -1.0) * 1.5 * push
        new_intra = float(np.clip(intra_c + 1.3 * cfg["sign"] * err, 2.0, 55.0))

        moved = False
        if base_layout is None:                              # hinh co dinh thi khong doi lop
            shapes, nl = _mk_shapes(new_layer)
            if abs(nl - layer_c) > 0.05: moved = True
            layer_c = nl
        colors, nt = _mk_colors(new_ntype)
        if abs(nt - ntype_c) > 0.05: moved = True
        ntype_c = nt
        if abs(new_intra - intra_c) > 0.1: moved = True
        intra_c = new_intra

        # BAO HOA = MOI nut dieu khien duoc da kich bien ma sai so van lon.
        # (Truoc day chi kiem tra intra_group — nut yeu nhat — nen bao "bao hoa" oan.)
        # QUAN TRONG: chi GAN CO, KHONG break. Ly do: dù nut da kich bien, moi vong van
        # lay mau lai voi seed khac -> van co co hoi bat duoc board tot hon. Break som o
        # day tung lam `win_rate 87 late` te di (lech 4.4 -> 9.1) vi mat 3 vong lay mau.
        if not moved and best[0] > cfg["tol"]:
            best[4]["saturated"] = True
            if verbose:
                print(f"    (moi nut lop/mau/intra da kich bien phan bo that — van lay mau tiep)")
    if best is not None and best[0] > cfg["tol"]:
        best[4].setdefault("saturated", True)      # target ngoai tam voi
    return best


def _print_layout(best, target_metric, target_value, stage):
    import json
    err, out, sj, ef, meta = best
    cfg = _METRIC[target_metric]; f = out["features"]
    print("\n" + "="*72)
    if meta.get("saturated"):
        print(f"  !! KHONG DAT MUC TIEU {target_value}{cfg['unit']} — tot nhat chi den {out[cfg['out']]:.1f}{cfg['unit']}"
              f" (lech {err:.1f}). Muc tieu vuot TRAN kha thi cho '{target_metric}' @ {stage}.")
        print("="*72)
    print(f"  LAYOUT {'(gan nhat)' if meta.get('saturated') else 'CHON'} — lech {err:.1f}{cfg['unit']} so voi muc tieu {target_value}{cfg['unit']}"
          f"  [{'TRONG' if meta['in_dist'] else 'NGOAI'} phan bo du lieu that]")
    print("="*72)
    star = target_metric
    print(f"  Hinh   : {meta['label']} | {int(ef['layerCount'])} lop"
          f"{' | DOI XUNG '+str(round(meta['sym']*100))+'%' if meta['sym']>0.999 else ''}")
    print(f"  Quan   : {int(ef['tileCount'])} | loai mau: {int(ef['n_types'])} ({meta['cc']} mau engine)")
    print(f"  Engine : intra_group={ef['intra_group']:.1f}  cover100={ef['cover100']:.1f}")
    print(f"  Do kho : beta = {out['beta']:+.2f}")
    print(f"\n  === {6 + (3 if out.get('undo_pct') is not None else 0)} CHI SO DU BAO @ {stage} (pos {_STAGE_POS[stage]}) ===")
    mk = lambda k: "  <== MUC TIEU" if k == star else ""
    print(f"    Win/Att %        : {out['win_att_pct']:5.1f} %    (+-{out['sai_so']['win_att']}){mk('win_att')}")
    print(f"    win_rate lan dau : {out['win_rate_dot1_pct']:5.1f} %    (+-{out['sai_so']['win_rate']}){mk('win_rate')}")
    print(f"    thoi luong       : {out['thoi_luong_phut']:5.2f} phut    (+-{out['sai_so']['thoi_luong']}){mk('thoi_luong')}")
    print(f"    revive user      : {out['revive_user_pct']:5.1f} %    (+-{out['sai_so']['revive']}){mk('revive')}")
    print(f"    booster (tong)   : {out['booster_pct']:5.1f} %    (+-{out['sai_so']['booster']}){mk('booster')}")
    print(f"    near_miss user   : {out['near_miss_pct']:5.1f} %    (+-{out['sai_so']['near_miss']}){mk('near_miss')}")
    if out.get('undo_pct') is not None:
        print(f"    -- Phan tach booster --")
        print(f"    undo             : {out['undo_pct']:5.1f} %    (+-{out['sai_so']['undo']}){mk('undo')}")
        print(f"    shuffle          : {out['shuffle_pct']:5.1f} %    (+-{out['sai_so']['shuffle']}){mk('shuffle')}")
        print(f"    magnet           : {out['magnet_pct']:5.1f} %    (+-{out['sai_so']['magnet']}){mk('magnet')}")
    print(f"\n  === BOT-NGUOI (20 lan x 3 muc ky nang) ===")
    for tp, lab in [(0.15, "gioi"), (0.5, "TB  "), (0.8, "yeu ")]:
        print(f"    {lab}: thang {f[f'bwin_{tp}']*100:3.0f}% | don duoc {f[f'bprog_{tp}']*100:3.0f}% board")
    out_path = os.path.join(HERE, "analysis", f"gen_{target_metric}_{int(target_value)}_{stage}.json")
    json.dump(dict(yeu_cau=dict(metric=target_metric, value=target_value, stage=stage),
                   hinh=meta['label'], color_count=meta['cc'],
                   doi_xung=meta['sym'], in_dist=meta['in_dist'],
                   engine_feats=ef, du_bao=out, board=sj),
              open(out_path, "w"), indent=1, default=str)
    print(f"\n  saved -> {os.path.relpath(out_path, HERE)}")


def _drift_banner():
    """In canh bao TROI MODEL o DAU moi lenh CLI.

    Skill khong co popup — canh bao phai la VAN BAN do tool in ra, va SKILL.md yeu cau
    Claude thuat lai nguyen van cho nguoi dung. Trang thai do scripts/eval_cohort.py
    --check-drift ghi ra analysis/drift_status.json."""
    p = os.path.join(HERE, "analysis", "drift_status.json")
    prov = M.get("PROVENANCE") or {}
    if not os.path.exists(p):
        if prov:
            print(f"[i] Model hieu chuan tu cohort '{prov.get('cohort')}' "
                  f"({prov.get('trained_at', '')[:10]}). CHUA kiem tra troi bao gio.")
            print("    Kiem: python scripts/eval_cohort.py <csv cohort moi> --check-drift --quiet\n")
        return
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        return
    st = d.get("status")
    if st == "WARN":
        print("!" * 78)
        print("  [!!] CANH BAO: MODEL DA TROI SO VOI DAN SO NGUOI CHOI MOI")
        print(f"  Moc hoc: {d.get('trained_on')} | kiem luc: {d.get('checked_at','')[:16]}")
        print(f"  {d.get('n_cohort_vuot')}/{d.get('tong_cohort_kiem')} cohort vuot nguong "
              f"{d.get('threshold')} diem | lech lon nhat {d.get('worst_drift')} diem")
        worst = sorted((d.get("per_cohort") or {}).items(),
                       key=lambda kv: -kv[1].get("worst", 0))[:3]
        for nm, v in worst:
            print(f"    - {nm}: lech toi da {v.get('worst')} diem ({v.get('n_breach')} o vuot)")
        print("  => Ket qua duoi day VAN DUNG cho dan so cu, nhung co the LECH voi dan so moi.")
        print("     Can nhac: python scripts/recalibrate.py <csv moi> --cohort <ten> --dry-run")
        print("!" * 78 + "\n")
    elif st == "WATCH":
        print(f"[~] Co dau hieu troi nhe (lech lon nhat {d.get('worst_drift')} diem, "
              f"nguong {d.get('threshold')}). Chua can hieu chuan lai.\n")
    elif st == "OK":
        print(f"[OK] Model con dung — da kiem tren {d.get('tong_cohort_kiem')} cohort, "
              f"lech lon nhat {d.get('worst_drift')} diem (< {d.get('threshold')}).\n")


if __name__ == "__main__":
    _drift_banner()
    if len(sys.argv) >= 2 and sys.argv[1] == "info":
        # In tu MODEL DANG DUNG (nguon song), khong chep so vao docstring — xem
        # ARCHITECTURE.md P8: chep so cung = tai lieu lech ngay lan hieu chuan ke tiep.
        _p = M.get("PROVENANCE")
        print('winrate_tool — "Tao level voi layout [X] co chi so [Y]=[Z] o giai doan [K]"\n')
        if _p:
            print(f"  Model hieu chuan tu cohort : {_p.get('cohort')}")
            print(f"  Thoi diem                  : {_p.get('trained_at')}")
            print(f"  So level fit               : {_p.get('n_levels')} "
                  f"{_p.get('n_levels_by_stage')}  (L{_p.get('level_min')}-L{_p.get('level_max')})")
            print(f"  So nguoi choi              : {_p.get('n_users'):,}")
            print(f"  Can bang trong so giai doan: {_p.get('stage_balanced')}")
            print(f"  Tang KHONG duoc hieu chuan : {_p.get('layers_NOT_refit')}")
        else:
            print("  (!) Model KHONG co PROVENANCE — khong ro hieu chuan tu cohort nao.")
            print("      Chay: python scripts/recalibrate.py <csv> --cohort <ten>")
        _ms, _cv = M.get("MAE_STAGE", {}), M.get("MAE_STAGE_CV", {})
        print(f"\n  === SAI SO {len(_ms)} CHI SO Y ===")
        print(f"  {'chi so':<13}{'early':>16}{'mid':>16}{'late':>16}")
        print(f"  {'':13}{'in-sample / CV':>16}{'in-sample / CV':>16}{'in-sample / CV':>16}")
        print("  " + "-" * 61)
        for _k in _ms:
            _row = f"  {_k:<13}"
            for _s in ("early", "mid", "late"):
                _a, _b = _ms[_k].get(_s), _cv.get(_k, {}).get(_s)
                _row += f"{(f'{_a:.2f}' if _a is not None else '-') + ' / ' + (f'{_b:.2f}' if _b is not None else '-'):>16}"
            print(_row)
        print("\n  CV = kiem dinh cheo 5-fold (trung thuc hon in-sample). Bao cao nen dung CV.")
        print("  Chi so cang THAP cang tot. Don vi: % (rieng thoi luong: phut).")
        print("\n  Hieu chuan lai : python scripts/recalibrate.py <csv> --cohort <ten> --dry-run")
        print("  Tra vung kha thi truoc khi gen: data-v2/metric_coverage.html")
    elif len(sys.argv) >= 3 and sys.argv[1] == "gen":
        # gen <metric> <value> <stage> [sym] [--layout N]
        metric = sys.argv[2]
        value = float(sys.argv[3]); stage = sys.argv[4]
        rest = sys.argv[5:]
        sym = any(a in ("sym", "symmetric", "doixung") for a in rest)
        base = None
        if "--layout" in rest: base = int(rest[rest.index("--layout")+1])
        best = gen_layout(metric, value, stage, symmetric=sym, base_layout=base)
        if best is None: print("KHONG sinh duoc layout nao."); sys.exit(1)
        _print_layout(best, metric, value, stage)
    elif len(sys.argv) >= 4 and sys.argv[1] == "target":
        z, st = float(sys.argv[2]), sys.argv[3]
        which = sys.argv[4] if len(sys.argv) > 4 else "win_rate"
        if which not in ("win_rate", "win_att", "win_rate_per_att"):
            print(f"Bai toan nguoc (theo beta) chi ho tro 'win_rate' hoac 'win_att'.")
            print(f"Dung predict()/gen de do '{which}' cho mot layout cu the.")
            sys.exit(1)
        b = required_difficulty(z, st, which)
        kind = "all" if which in ("win_att", "win_rate_per_att") else "att1"
        mkey = "win_att" if kind == "all" else "att1"
        nm = "Win/Att %" if kind == "all" else "win_rate lan choi dau"
        print(f"MUC TIEU: {nm} = {z}% o giai doan '{st}'")
        print(f"  => layout can do kho beta = {b:+.2f}\n")
        print(f"  CUNG layout do dat o giai doan khac (theta DONG theo phieu song sot):")
        for s in ["early", "mid", "late"]:
            th = _theta(kind, _STAGE_POS[s], s)
            p = np.mean(1/(1+np.exp(-(M["B0"] + th - b)))) * 100
            # uu tien MAE kiem dinh cheo (trung thuc hon in-sample); lam tron 2 so
            _e = (M.get("MAE_STAGE_CV", {}).get(mkey, {}).get(s)
                  or M["MAE_STAGE"][mkey][s])
            print(f"    {s:6s} -> {nm} ~ {p:5.1f}%   (sai so +-{_e:.2f} diem)")
    else:
        print(__doc__)
