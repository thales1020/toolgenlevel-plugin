# tile-puzzle — Kịch bản test (live)

Mục đích: kiểm **routing** (prompt của designer nổ đúng skill?) và **pipeline** (ảnh→level có nối 2 skill?).
Các test tự động (parity, self-test) chỉ kiểm code chạy được — **KHÔNG** kiểm routing. Routing chỉ test được
khi chạy thật, vì model quyết định dựa trên `description`/`when_to_use` (D1).

---

## 0. Pre-flight (tự động — chạy trước)

```bash
# engine 2 skill còn đồng bộ?
python tile-puzzle/tests/check_engine_parity.py          # kỳ vọng: parity OK (7 files)

# từng skill còn chạy?
python tile-puzzle/skills/gen-layout/scripts/test_full.py # kỳ vọng: 12/12 PASS

# manifest + frontmatter hợp lệ?  ❗CHẠY ĐẦU TIÊN — bắt lỗi YAML frontmatter
claude plugin validate ./tile-puzzle      # FAIL = description/when_to_use bị bỏ ở runtime (B6)
```
**`claude plugin validate` là check QUAN TRỌNG NHẤT** — colon/ký tự lạ trong `description`/`when_to_use`
không quote sẽ làm YAML parse fail và **drop toàn bộ metadata âm thầm** (routing hỏng mà không báo lỗi).
Chạy nó **sau mỗi lần sửa frontmatter**. Cả 4 xanh thì sang phần routing.

## 1. Khởi động + cách nhận biết skill nào nổ

```bash
claude --plugin-dir ./tile-puzzle
```
Với mỗi prompt, **quan sát**:
- Claude nạp skill nào? (`/tile-puzzle:gen-layout` hay `/tile-puzzle:tile-level-design`)
- Nó chạy script từ thư mục skill nào? (`gen-layout/scripts/...` vs `tile-level-design/...`)
- **Output là gì?** Layout rỗng (`NewLayout_*.json`, không tile) **hay** level chơi được (có tile + score + v3-solvable)?

Ghi lại: skill thực tế nổ + output, so với cột "kỳ vọng".

---

## 2. Nhóm A — Routing đơn (phải đậu 100%)

| ID | Prompt (gõ vào) | Skill kỳ vọng | Đậu khi | KQ |
|---|---|---|---|---|
| A1 | `tạo một màn chơi dễ` | tile-level-design | ra **level có tile** (dùng 1 sample layout), không hỏi layout | |
| A2 | `tạo layout hình khiên đối xứng` | gen-layout | ra **1 layout rỗng**, in `symmetry: … best vertical≈1.00` (bulk đã bỏ — compose từng cái) | |
| A3 | `màn này giải được không?` (kèm 1 file level) | tile-level-design | chạy v3 → True/False | |
| A4 | `phân tích độ khó màn này` (kèm level) | tile-level-design | in 5-component score (analyze) ⟵ GAP1 | |
| A5 | `chuẩn hóa file level này` | tile-level-design | normalize + inject metadata ⟵ GAP1 | |
| A6 | `màn này khó quá, làm dễ lại` | tile-level-design | giảm độ khó, vẫn solvable ⟵ GAP1 | |
| A7 | `cho tôi 20 màn test` | tile-level-design | ra **20 level** (không phải 20 layout rỗng) ⟵ GAP3 | |
| A8 | `tạo layout hình trái tim` | gen-layout | ra **layout rỗng** hình tim (no tile) | |

## 3. Nhóm B — Pipeline cross-skill (GAP 2 — rủi ro cao nhất)

Đậu = **cả 2 skill nổ tuần tự** và kết quả cuối là **level chơi được**, không phải layout rỗng.

| ID | Prompt | Kỳ vọng | Đậu khi | KQ |
|---|---|---|---|---|
| B1 | `làm màn chơi hình con vịt` | gen-layout → tld | gen-layout dựng hình vịt → tld gán tile → level solvable | |
| B2 | `biến logo này thành màn chơi` (kèm ảnh) | gen-layout → tld | image→layout→level | |
| B3 | `màn chơi theo hình này, độ khó ~50` (kèm ảnh) | gen-layout → tld + target score | level đạt score ~50 (±), solvable | |
| B4 | `màn theo ảnh, 50% tile bị che 100%` | gen-layout → tld + cover | level đạt cover100 ≈ 50% | |
| B5 | `ảnh đơn giản này thành màn rất khó (score 150)` | phát hiện **bất khả** | **KHÔNG ship bừa**: chẩn đoán "trần ảnh < 150" + hỏi nới constraint (§Pipeline điểm 5) | |

**Nếu B1/B2 chỉ nổ gen-layout** (ra layout rỗng, designer tưởng hỏng) → đó là GAP 2 hiện hình → báo lại để mạnh hóa nudge trong description/when_to_use.

## 4. Nhóm C — Ca mơ hồ / biên

| ID | Prompt | Kỳ vọng | Đậu khi | KQ |
|---|---|---|---|---|
| C1 | `tạo level` (không nói gì thêm) | tile-level-design | ra 1 level (mặc định dễ) — KHÔNG nổ gen-layout | |
| C2 | `score 100 + solvable, layout L109` | tile-level-design (P6) | level score~100, v3=True | |
| C3 | `tạo trap ẩn 90% fail` | tile-level-design (P1) | trap solvable + greedy fail ≥90% | |

---

## 5. Tiêu chí đậu & xử lý khi rớt

- **Nhóm A + C**: kỳ vọng **đậu hết**. Rớt = routing sai → đây là lỗi description, sửa được.
- **Nhóm B**: B5 (conflict) và chaining là khó nhất; chấp nhận cần vài lần chỉnh.

**Khi 1 test rớt**, ghi lại 3 thứ: (1) prompt nguyên văn, (2) skill **thực tế** nổ, (3) skill **kỳ vọng**.
→ Sửa: thêm/bớt trigger trong `when_to_use` của skill đúng, hoặc thêm câu "NOT for… — that is <skill kia>"
ở skill bị nổ nhầm. Đây là vòng **observe-Claude-B → refine** mà best-practices khuyến nghị (lặp tới khi ổn).

## 6. Giới hạn đã biết (đừng coi là bug)

- **Chaining (B1–B4) không thể đảm bảo 100% bằng description** — D4: skill không gọi skill; model luồng chính
  phải tự nối. Description đã nudge mạnh nhất có thể ("gen-layout runs first… then this skill").
- Test này kiểm **hành vi routing**, không kiểm chất lượng level (độ khó/đối xứng có test riêng).
