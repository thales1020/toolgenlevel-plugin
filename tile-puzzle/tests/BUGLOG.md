# tile-puzzle — Bug log (live test, fix 1 lượt)

Lỗi gom từ phiên test (Claude B). **Routing đúng** (tile-level-design nổ cho "màn dễ"); lỗi nằm ở
**execution** — model tự VIẾT script improvised sai API thay vì dùng template/recipe có sẵn. → đây là
**lỗi chất lượng skill** (guidance + API chưa đủ rõ để model khỏi bịa code sai).

## ✅ ĐÃ FIX 1 lượt (2026-06-23) — verified
- **B1** ✅ tld SKILL.md §3: doc cấu trúc `compute_full_score` (component scalars + `final_score` + `weights` DICT) — "never round the whole dict".
- **B2/B3** ✅ ship `templates/gen_test_set.py` (chạy 5/5 v3-solvable trong **2s**, spread band 0.7..85; thay bản bịa timeout 580s) + pointer ở §3/§12.
- **B4** ✅ `empirical_gen._in_envelope` + `MAX_ASPECT=1.05`: reject w/h>1.05 → empirical/symmetric/mixed hết phình ngang (đo: max aspect 1.00).
- **B5** ✅ `claude_compose` nhánh `mirror=True` dùng `geom_symmetrize`+`geom_div3_trim` → khiên **geom-sym=1.0**; nhánh `mirror=False` (kiếm) giữ chéo. SKILL.md §3: bước CLASSIFY symmetry (đối xứng→mirror; dài→diagonal, lo luôn B4).
- **dọn** ✅ xóa 3 stray script.
- **B6** ✅ ❗CRITICAL — `claude plugin validate` bắt: **YAML frontmatter CỦA CẢ HAI skill parse FAIL**
  → *"all frontmatter fields silently dropped"*. Nguyên nhân: **colon-space `: ` trong value không
  quote** (gen-layout "Upstream tool: outputs"; tld "simulator: assign") → YAML tưởng nested map. Hệ quả:
  description/when_to_use **bị bỏ ở runtime trong MỌI commit trước** → routing chạy trên metadata rỗng;
  mọi GAP-fix/description **chưa hề có hiệu lực**. Fix: **bọc 2 value trong `"..."`**. `claude plugin
  validate` giờ PASS. → Bài học: **luôn chạy `claude plugin validate` sau mỗi sửa frontmatter** (suy luận
  không bắt được; chỉ validator thật bắt). Cần **re-test routing live** vì description giờ mới thực bật.
- Verify: parity OK · gen-layout test_full 12/12 · shield 1.0 · sword diagonal · gen_test_set 2s · **plugin validate PASS**.

## Stray files cần dọn (Claude B viết vào `templates/`, untracked, hỏng)
- `gen_easy_once.py` (72 dòng) — lỗi B1+B2
- `gen_test_set.py` (101 dòng) — lỗi B3
- `gen_hard_L20.py` — chưa rõ, dọn luôn

---

## B1 — `compute_full_score` cấu trúc bị hiểu sai  ❗(root cause chính)
**Symptom:** `TypeError: dict doesn't define __round__` tại `{k: round(v,2) for k,v in sc.items()}`.
**Sự thật (đã verify):** `compute_full_score` trả về keys:
`layout(float) inter_group(float) intra_group(float) cover100(int) pickable_diversity(int)
stripped(int) final_score(float) remaining_tiles(int) weights(DICT)`.
→ Có **`weights` là dict lồng** + vài key meta (`stripped`/`remaining_tiles`) — không phải toàn float
thành phần. Code bịa `round` hết mọi value → chết ở `weights`.
**Fix dự kiến:** (a) ghi rõ cấu trúc return này trong SKILL.md (mục scoring); (b) recipe chuẩn chỉ
lấy đúng key thành phần, không iterate-round-all (analyze_level.py / §16 vốn làm đúng — model đã không tái dùng).

## B2 — `board=None` → `.all_cells()`
**Symptom:** `'NoneType' object has no attribute 'all_cells'` (code inline của Claude B).
**Root cause:** loader trong code bịa trả None (dùng sai hàm / sai board_idx). `load_board_from_file` chuẩn
thì OK (đã verify). Model không copy đúng loader.
**Fix dự kiến:** recipe quickstart copy-paste-đúng dùng `load_board_from_file` + reset tile, để model khỏi bịa.

## B3 — generator improvised CHẬM + toàn "Very Easy / ngoài band"
**Symptom:** `gen_test_set.py` chạy 580s → **timeout (Exit 124)**; mọi level ra `score<4` "Very Easy
(best-effort, ngoài band)".
**Root cause:** đúng bẫy SKILL.md §15 đã cảnh báo ("inline P6 default is EASY" — color_count thấp, không
chỉnh distance/hard_code) + loop seed không early-term → vừa dễ vừa chậm. Cảnh báo có nhưng model vẫn dính.
**Fix dự kiến:** ship 1 script chuẩn `gen_test_set.py` (đúng knobs theo band + early-term + nhanh) để model
**chạy** thay vì **viết lại**; hoặc recipe "N test levels" prescriptive với knob mặc định không-dễ.

---

## Root cause chung
Model fresh **improvise script** thay vì dùng bundled template/recipe → vấp (1) score-structure không doc,
(2) loader sai, (3) easy-default + loop chậm. Best-practices: *"provide utility scripts — more reliable than
generated code; solve, don't punt."*

## Kế hoạch fix 1 lượt (chờ user chốt "fix now")
1. Dọn 3 stray script hỏng.
2. SKILL.md: **doc cấu trúc `compute_full_score`** (key + `weights` dict + `final_score`).
3. SKILL.md: thêm **Quickstart recipe** copy-paste-đúng cho 2 ca hay nhất ("1 màn dễ", "N màn test") —
   loader đúng + key score đúng + knob không-dễ + early-term (nhanh).
4. (Tùy chọn) ship `gen_easy.py` + `gen_test_set.py` bản chuẩn làm template để model chạy thẳng.

## B4 — gen-layout sinh layout PHÌNH NGANG, sai use-case mobile (portrait) ❗
**Vấn đề (user):** game chạy trên điện thoại → màn **dọc**. Layout rộng hơn cao (phình ngang) là **vô lý**.
**Sự thật (đã verify):** `empirical_gen._in_envelope` chặn `width(4,9)` & `height(4,10)` **ĐỘC LẬP, KHÔNG
chặn tỷ lệ w/h** → một layout `width 9 × height 4` (aspect 2.25, rất ngang) **vẫn pass**. EXPERIENCES [3]
("aspect ~0.88") và [7] ("orient slightly TALL") chỉ là **guidance mềm cho compose (Claude)**, KHÔNG enforce
trong code bulk (empirical/symmetric/mixed đều qua `_in_envelope`).
**Fix dự kiến:**
1. Thêm ràng buộc **aspect vào `_in_envelope`**: reject `w/h > ~1.0` (chỉ portrait/square, ưu tiên cao≥rộng)
   → phủ luôn empirical + symmetric + mixed (cả 3 dùng chung hàm này).
2. compose: thêm check aspect trong `claude_compose` + ghi rõ trong SKILL.md/EXPERIENCES: **"mobile portrait —
   width ≤ height, NEVER wide"** (hard rule, không chỉ ~0.88 mềm).
3. Cân nhắc thêm cờ `--max-aspect` (mặc định ~1.0) để chỉnh được.
**Lưu ý:** đây là fix **gen-layout** (B1–B3 là tile-level-design) → đợt fix-1-lượt giờ chạm **cả 2 skill**.

## B5 — compose mode: shape đối xứng (khiên) ra "vài ô chưa đối xứng" ❗
**Symptom (user):** gen chiếc khiên (lẽ ra đối xứng trái-phải) nhưng còn **vài ô lệch**.
**Sự thật (đã verify):** `claude_compose.compose()` mirror nửa hình (OK) **rồi** trim về bội-3 bằng cách
**bỏ 1–2 ô "topmost, farthest"** (dòng 37–42) + support-cleanup — cả hai **bỏ ô lẻ một bên** → vỡ đối xứng
đúng 1–2 ô. **Cùng họ bug** với "gần đối xứng" của `empirical` (đã fix cho bulk qua `gen_symmetric`), nhưng
**compose mode chưa được fix**.
**Fix dự kiến:** khi `mirror=True`, compose dùng **trim giữ-đối-xứng** — bỏ **cặp gương** (hoặc 1 ô trên
trục x=0 cho ca %3==1) + cleanup đối xứng. Tái dùng `gen_symmetric.geom_div3_trim` / `geom_symmetrize`
(đã có sẵn, đã test) thay cho trim lẻ hiện tại.

**Tinh chỉnh (user):** lỗi này CHỈ xảy ra với **prompt thuần văn bản**; đưa **ảnh** thì vẫn ra đối xứng
(mask đã mang sẵn đối xứng). → Fix KHÔNG phải "luôn ép mirror". Với prose, Claude (generator) phải **phân
loại vật thể trước**:
- **Đối xứng** (khiên, tim, ly…) → mirror=True + trim giữ-đối-xứng (B5 fix) → đối xứng tuyệt đối.
- **Dài/bất đối xứng** (kiếm, chìa khóa, mũi tên…) → **KHÔNG mirror**; làm **chéo/nghiêng sang 1 bên** →
  vừa tự nhiên vừa **tối ưu khung hình mobile-portrait** (nằm ngang = phình ngang = vi phạm B4; chéo thì gọn
  trong khung dọc). EXPERIENCES [2] đã có "elongated → DIAGONAL" — **nối với B4** + ghi thành bước phân-loại
  bắt buộc trong SKILL.md compose.
→ Tóm: fix compose = (1) bước phân-loại symmetry từ prose; (2) nhánh đối xứng dùng geom-trim; (3) nhánh dài
dùng diagonal-tilt (đồng thời lo aspect B4).

## Open question — ĐÃ QUYẾT: KHÔNG dùng advisor (2026-06-23)
**Có nên "bật advisor"?** → **Không.** Không gắn bước advisor/review-bằng-reviewer vào workflow skill.
(Lý do cân nhắc lúc trước: chất lượng↑ nhưng tốn token + độ trễ mỗi lần gen, và advisor kiểm *thiết kế*
chứ không thay test thật — B6 là minh chứng: chỉ `claude plugin validate` mới bắt, advisor thì không.)

## Thêm bug? Ghi tiếp xuống dưới
- (chờ user test thêm)
