# Refactor Plan — gen-layout & tile-level-design

Bám theo `ARCHITECTURE.md`. Mỗi việc gắn nhãn luật (D*/P*/§*) để truy ngược.
**Thước đo thành công** = sau refactor, 4 thao tác vòng đời (§4) rẻ hơn; test xanh; SKILL.md sync code.
**Phạm vi:** Tầng 1 + 2. Tầng 3 (reorg thư mục) **hoãn** (§5). Plugin **hoãn** (còn [OPEN] §6).

---

## Giả định đã chốt (override nếu cần)

| # | Quyết định | Default chọn | Lý do |
|---|---|---|---|
| A1 | `find_bridge_hard_L21.py` (ref gãy §17 tld) | **Gỡ tham chiếu** | §17 vốn đã có caveat; trung thực hơn là vờ có file (P7) |
| A2 | Scope `tile-level-design` (User vs Project) | **Giữ Project, xóa User** | Đi theo repo; bản 2 nơi đang byte-identical (D6) |
| A3 | engine nhân đôi 2 skill | **Để yên lần này** | DRY thật chỉ giải bằng plugin đang [OPEN]; chấp nhận tạm (P4) |

---

## Phase 0 — Baseline an toàn (P7)

*Không compiler → test là lưới duy nhất; chốt mốc xanh trước khi sửa.*

- [ ] `gen-layout`: chạy `scripts/test_full.py` → kỳ vọng 12/12.
- [ ] `tile-level-design`: `scripts/analyze_level.py` trên 1 example + 1 `solve_v3` smoke → True.
- **Gate:** cả hai xanh thì mới sang Phase 1.

---

## Phase 1 — Tầng 1: Đúng & sạch (rủi ro thấp)

### gen-layout
| # | Việc | Luật | Acceptance |
|---|---|---|---|
| 1.1 | Đóng **nợ drift**: thêm `--mode symmetric` + `--mode mixed` vào SKILL.md (bảng mode §4 + 1 ví dụ lệnh mỗi mode) | P7, §4-CẢI TIẾN | `grep` thấy cả 2 mode trong SKILL.md; mô tả khớp `gen_layouts.py --mode` |
| 1.2 | Fix `load_board_from_path` → `load_board_from_file` (dòng 110) | P7 | không còn `load_board_from_path` trong SKILL.md |
| 1.3 | Thêm `.gitignore` (`__pycache__/`, `*.pyc`, `desktop.ini`); xóa cruft; **xóa zip lồng** `gen-layout-skill.zip` | §3 | `find` không còn pyc/desktop.ini/zip-lồng trong skill |

### tile-level-design
| # | Việc | Luật | Acceptance |
|---|---|---|---|
| 1.4 | Fix `load_board_from_path` → `load_board_from_file` (§1.5) | P7 | hết `load_board_from_path` |
| 1.5 | Bỏ path cứng `c:/Users/PC1150/.../GD_Test` (§19) | D5, P7 | hết chuỗi `PC1150`/`GD_Test` máy-cũ trong SKILL.md |
| 1.6 | A1: gỡ ref `find_bridge_hard_L21.py` (§17), giữ phần mô tả variant + caveat | P7 | không còn trỏ file không tồn tại |
| 1.7 | `.gitignore` + xóa cruft (desktop.ini, __pycache__) | §3 | sạch như 1.3 |

- **Gate:** chạy lại Phase 0 → vẫn xanh.

---

## Phase 2 — Tầng 2: Đúng chuẩn tài liệu (rủi ro vừa)

| # | Việc | Luật | Acceptance |
|---|---|---|---|
| 2.1 | **Thiết kế lại description CỦA CẢ HAI cùng lúc** (contract-first) + thêm `when_to_use`; **tách trigger** — bỏ chỗ tld tự nhận "layout-shape levels (heart/animal)" giẫm gen-layout | **P2, D1, D7** | 2 description không còn từ-khóa chồng; mỗi cái ≤1024; desc+when_to_use ≤1536 |
| 2.2 | Ví dụ lệnh trong SKILL.md → `${CLAUDE_SKILL_DIR}/scripts/...` (cả hai) | D5 | không còn path tương-đối-tự-định-vị trong ví dụ SKILL.md |
| 2.3 | **Cô đọng** SKILL.md tld: đẩy chi tiết §18–21 (trùng `reference/`) xuống file tham khảo, giữ phần quyết-định-hành-động | **P6, D3** | SKILL.md tld giảm dòng, vẫn < 500; nội dung gỡ ra nằm trong `reference/` |
| 2.4 | A2: dedupe scope — xóa bản User `~/.claude/skills/tile-level-design` | D6 | `/context` chỉ còn 1 đăng ký tld |
| 2.5 | Ghi rõ **NewLayout JSON = contract** giữa 2 skill (1 đoạn ở cả 2 SKILL.md); xác nhận `validate_layout.py` phủ format | P5 | có mục "contract" ở 2 SKILL.md; `validate_layout.py` chạy pass trên 1 output gen-layout |

- **Gate:** chạy lại Phase 0 → vẫn xanh. Riêng 2.1 kiểm bằng đọc-lại (không có test tự động cho routing — P7 ghi nhận).

---

## Out of scope lần này (§5 — chống over-engineering)

- ❌ Reorg thư mục (`references/`/`assets/`, đổi tên `reference/`) — churn path mọi script, lợi ích cosmetic. Chỉ làm khi quyết plugin.
- ❌ Plugin / chia sẻ engine — [OPEN] §6, chưa test `${CLAUDE_PLUGIN_ROOT}`.
- ❌ Gộp 2 skill / framework chung — D8 + P1 phản đối.
- ❌ Bundle `boards_Full.zip` vào skill — chỉ GRPO cần; symmetric/mixed đã chạy offline qua cache. Ghi chú dependency là đủ.

---

## Traceability (issue → luật → task)

| Issue đã quét | Luật vi phạm | Task |
|---|---|---|
| SKILL.md gen-layout thiếu mode mới | P7 (drift) | 1.1 |
| `load_board_from_path` (2 skill) | P7 (broken ref) | 1.2, 1.4 |
| cruft pyc/desktop.ini/zip-lồng | §3 | 1.3, 1.7 |
| path cứng PC1150 | D5, P7 | 1.5 |
| ref `find_bridge_hard_L21` gãy | P7 | 1.6 |
| description chồng trigger | P2, D1 | 2.1 |
| path không theo chuẩn | D5 | 2.2 |
| SKILL.md tld dày/lặp | P6, D3 | 2.3 |
| trùng đăng ký User+Project | D6 | 2.4 |
| contract format chưa nêu rõ | P5 | 2.5 |

---

## Cách thực thi
- Mỗi Phase 1 commit nhỏ, message gắn nhãn luật (vd: `gen-layout: fix broken load_board ref [P7]`).
- Sau mỗi Phase chạy Gate test. Đỏ → dừng, sửa, không đi tiếp.
- Bắt đầu từ **gen-layout** (nhỏ, vừa động code → pilot chốt khuôn), rồi tld.
</content>
