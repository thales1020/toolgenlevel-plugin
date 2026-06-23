# Skill Architecture — ToolGenLevel

Bộ luật thiết kế cho các skill trong repo này (`gen-layout`, `tile-level-design`, và skill tương lai).
Mục tiêu của kiến trúc **không** phải "đẹp" — mà là làm cho 4 thao tác vòng đời **rẻ và an toàn**:
**cải tiến · thêm · xóa · thay thế** một skill (xem §4). Mọi luật bên dưới được biện minh bằng một
trong hai: một sự thật có tài liệu, hoặc một suy luận được giải thích.

## Quy ước nguồn (đọc trước)

- **[DOC]** — Có trong tài liệu chính thức Claude Code / Agent Skills, kèm URL ở §6. Thu thập qua một
  research pass (2026-06-22); tôi trích URL chứ chưa tự fetch lại từng cái — coi là "có nguồn, chưa tái kiểm".
- **[INFER]** — Suy luận của tôi từ tư duy kiến trúc phần mềm. KHÔNG có trong tài liệu skill. Mỗi chỗ
  [INFER] đều kèm **chuỗi lý do** để bạn tự thẩm, có thể bác.
- **[OPEN]** — Chưa chắc, cần test thực tế trước khi tin. Liệt kê ở §5.

---

## 1. Ràng buộc nền tảng (sự thật phải tôn trọng) — [DOC]

Đây là "luật vật lý" của platform; mọi quyết định thiết kế phải nằm trong khung này.

| # | Sự thật | Nguồn |
|---|---|---|
| D1 | **Routing chỉ dựa vào `description`** (+ `when_to_use`). Không có cơ chế phá-hòa khi 2 description chồng nhau. | [skills.md#frontmatter] |
| D2 | **Progressive disclosure 3 tầng**: metadata (name+description, luôn nạp) → SKILL.md (nạp khi skill khớp) → file phụ trong `reference/`/`scripts/` (nạp khi được tham chiếu). *Cơ chế là [DOC]; con số token cụ thể (~100/<5000/25k) KHÔNG có trong doc — xem §6.* | [best-practices] |
| D3 | **SKILL.md nên < 500 dòng**; file phụ **không tốn token tới khi được gọi**. | [best-practices] |
| D4 | **Không có cơ chế skill gọi skill.** Composition chỉ qua: file phụ trong cùng skill; `context: fork`; hoặc subagent preload (`agents/x.md` khai báo `skills:[...]`). Không có khái niệm "sub-skill"/mode phân cấp — nhưng SKILL.md **được phép rẽ nhánh** bằng prose. | [skills.md], [sub-agents.md] |
| D5 | **Path chuẩn: `${CLAUDE_SKILL_DIR}/...`** (forward slash, nông 1 cấp). Cho `script` chạy bằng Bash. | [skills.md#substitutions] |
| D6 | **Scope precedence**: enterprise > personal > project; plugin thì **namespaced** `/plugin:skill`. Cùng tên ở 2 scope = nhân bản, bản ưu tiên thắng nhưng cả hai vẫn hiện trong listing. | [skills.md#where-skills-live] |
| D7 | Frontmatter: `name` ≤64 (kebab), `description` ≤1024; `description`+`when_to_use` ≤1536 cho listing. | [skills.md], [agentskills spec] |
| D8 | **Plugin = đóng gói để chia sẻ/phân phối/đa-project/versioned** (KHÔNG phải về DRY/code-share). `skills/` layout cho plugin >1 skill. Plugin skill **namespaced** `/plugin:skill`. *(Luận điểm "tách nếu độc lập / gộp nếu output luôn feed" là [INFER] — xem ghi chú dưới P1.)* | [plugins.md] |

---

## 2. Nguyên lý thiết kế (kiến trúc phần mềm, áp vào skill)

Mỗi nguyên lý ghi rõ: ý gốc bên SW → vì sao đúng ở đây → tựa vào sự thật [DOC] nào.

**P1 — Một skill = một năng lực (SRP).** [INFER — KHÔNG có trong doc, suy luận thuần]
*Lý do:* SRP nói "một module, một lý do để đổi". `gen-layout` đổi khi cách dựng hình học đổi;
`tile-level-design` đổi khi luật gán tile/chấm điểm đổi — **hai trục thay đổi độc lập**. Gộp lại thì
một thay đổi hình học buộc tái kiểm cả phần chấm điểm.
*Kiểm chứng độc lập:* có thể gán tile lên 120 `sample_layouts` có sẵn mà **không cần** gen-layout →
chúng độc lập về dùng → giữ tách.
*Quy tắc quyết (suy luận, doc KHÔNG phát biểu):* tách nếu mỗi skill **dùng độc lập được**; chỉ cân nhắc gộp
khi output skill này **luôn luôn** là input skill kia. Bác được nếu bạn thấy sai.

**P2 — `description` là CONTRACT, viết interface-first.** [INFER, tựa D1]
*Lý do:* Vì D1 nói router chỉ nhìn description, nó đóng vai trò y hệt **API signature**: caller (router của
model) bind vào đó. Hai description chồng nhau = "overload nhập nhằng" mà **không có compiler/linker
báo lỗi** — chỉ trôi vào routing sai. → Mỗi skill phải có một câu "WHAT + WHEN" phân biệt được; dùng
`when_to_use` để tách điều kiện kích hoạt. Đây là lý do `tile-level-design` không được tự nhận
"tạo layout hình..." (giẫm chân gen-layout).

**P3 — Phân tầng, phụ thuộc hướng vào lõi ổn định.** [INFER, tựa D2]
```
engine/      ← LÕI ổn định (solver, scorer). Đổi hiếm, đổi là nguy hiểm (nhiều thứ phụ thuộc).
scripts/     ← tầng ứng dụng. Gọi engine. Đổi vừa.
SKILL.md     ← tầng điều phối/“mặt tiền”. Đổi thường xuyên, rẻ.
```
*Lý do:* Clean/Layered architecture — phụ thuộc chỉ hướng **vào trong**, không bao giờ engine biết tới
SKILL.md. Khớp với D2: SKILL.md là tầng hay-đổi-và-tốn-token ở ngoài; engine là tầng nạp-khi-cần ở trong.
*Hệ quả vận hành:* sửa SKILL.md thoải mái; sửa engine phải chạy test (§2 P7) vì cả 2 skill tựa vào nó.

**P4 — DRY cho code dùng chung: một vị trí, không copy.** [INFER]
*Lý do:* engine hiện **byte-identical ở 2 skill** = nhân bản → rủi ro drift (sửa một bên quên bên kia).
DRY: trích về một nguồn. *Cảnh báo (đã kiểm doc, §6):* **plugin KHÔNG tự giải DRY engine** — không có biến cho
skill với tới engine cấp plugin-root; chỉ có `bin/` cho executable, hoặc vẫn nhân đôi engine. Nên lần này
**chấp nhận nhân đôi tạm** (giả định A3); DRY thật chờ một cách đóng gói khả thi. KHÔNG phải lý do **gộp logic** (P1).

**P5 — Ghép qua data-contract (format file), không gọi trực tiếp.** [INFER, tựa D4]
*Lý do:* D4 cấm skill gọi skill. Nhưng đó không phải hạn chế — nó **ép** đúng triết lý Unix: tool nhỏ,
ghép qua một format chung. `gen-layout` xuất `NewLayout_*.json`; `tile-level-design` đọc đúng format đó.
**Format JSON đó CHÍNH LÀ interface giữa hai skill** — phải coi nó như một API: versioned, ổn định, có
validate. Đổi format = breaking change cho mọi consumer.

**P6 — Token = hot path; ngắn gọn là HIỆU NĂNG, không phải thẩm mỹ.** [INFER — chỗ SW *gãy*]
*Giải thích kỹ (vì đây là chỗ khác SW):* Trong SW, comment/doc dài đọc một lần lúc compile, gần như free.
Ở skill, mỗi dòng SKILL.md là chi phí **lặp lại mỗi lần skill active** (D2/D3) — giống code nằm trong vòng
lặp nóng. Nên đánh đổi "rõ ràng dài dòng" mà SW chấp nhận thì ở đây **bị phạt nặng**. Quy tắc: thông tin
quyết-định-hành-động ở SKILL.md; chi tiết tham khảo đẩy xuống `reference/` (D2 cho nạp lazy).

**P7 — Không có compiler → test + convention là lưới an toàn.** [INFER — chỗ SW *gãy*]
*Giải thích kỹ:* Bug `load_board_from_path` (tên hàm không tồn tại) — bên SW compiler/IDE chặn ngay; ở
skill nó trôi vào runtime vì "code" là prose cho LLM đọc. Hệ quả: **không có safety net tĩnh**. Bù lại bằng:
(1) test-suite chạy được (cả 2 skill đã có — `test_full.py`, v.v.), (2) convention nhất quán để giảm bề mặt
lỗi, (3) doc phải sync code (drift = bug). Đây là lý do §3 ép một khuôn cấu trúc cố định.

---

## 3. Khuôn cấu trúc chuẩn (mọi skill theo đúng)

```
<skill>/
  SKILL.md            # < 500 dòng; WHAT/WHEN + rẽ nhánh; “chạy X” (không “xem X”); path = ${CLAUDE_SKILL_DIR}
  reference/          # *.md đọc-khi-cần (chi tiết tách khỏi SKILL.md theo P6/D2)
  scripts/            # *.py CHẠY bằng Bash (D5)
  data/               # json/csv/template tĩnh (tùy chọn — doc KHÔNG lập "assets/" làm chuẩn)
  engine/             # lõi dùng chung (P3); một nguồn (P4)
  .gitignore          # chặn __pycache__, *.pyc, desktop.ini
```
*Vì sao cố định khuôn:* P7 — convention thay cho compiler. Hai skill cùng khuôn thì thao tác §4 (nhất là
"thêm" và "thay") chỉ là lặp một mẫu đã biết, ít chỗ sai.
*Tên thư mục:* doc chỉ chắc **`reference/` (SỐ ÍT)** + `scripts/` (ví dụ chính thức best-practices);
`assets/`/`data/` KHÔNG phải chuẩn doc. tile-level-design vốn dùng `reference/` → đã đúng, **không đổi tên**.

---

## 4. Playbook vòng đời (thước đo thật của kiến trúc)

Kiến trúc tốt = 4 thao tác này rẻ. Mỗi bước ghi nguyên lý nào khiến nó an toàn.

**CẢI TIẾN một skill.**
- Đổi hành vi → sửa `SKILL.md`/`scripts` (tầng ngoài, P3 → rẻ). Đổi solver/scorer → sửa `engine`, **bắt buộc
  chạy test** trước khi tin (P7), vì nhiều thứ phụ thuộc (P3).
- Sau khi sửa code, **sync SKILL.md** ngay (P7: drift = bug). *Ví dụ đang nợ:* gen-layout vừa thêm
  `--mode symmetric/mixed` nhưng SKILL.md chưa ghi → phải đóng.

**THÊM một skill.**
1. Viết `description` trước (P2, contract-first). Đối chiếu description các skill hiện có — **không được
   chồng trigger** (D1). Nếu chồng, hoặc làm rõ ranh giới, hoặc nó nên là **mode trong skill cũ**, không
   phải skill mới.
2. *Quyết "skill mới vs mode trong skill cũ"* (D8): độc lập-dùng-được → skill mới; output luôn-feed skill
   khác và không dùng riêng → mode/nhánh trong skill đó.
3. Dựng theo khuôn §3; tái dùng `engine` qua một nguồn (P4).

**XÓA một skill.**
- Vì các skill **lỏng-coupling qua format file** (P5), không qua lời gọi trực tiếp (D4), xóa một skill chỉ
  ảnh hưởng **consumer của format nó xuất ra**. Kiểm: ai đọc format đó?
- An toàn: để lại `SKILL.md` mỏng deprecation trỏ sang cái thay thế (1 vòng), rồi mới xóa hẳn. Dọn luôn
  bản nhân bản scope nếu có (D6).

**THAY THẾ một skill (đổi ruột, giữ vỏ).**
- Giữ nguyên **2 contract**: `description` (P2) và **format file xuất ra** (P5). Thay toàn bộ `engine/scripts`
  bên trong → mọi caller (router) và consumer (skill đọc output) **không hề hay biết**.
- Đây là Liskov/interface-stability: thay implementation sau một interface ổn định. Chính 2 contract này là
  thứ khiến "thay" rẻ — nên đừng bao giờ đổi chúng tùy tiện.

---

## 5. Cố tình KHÔNG làm (chống over-engineering)

Liệt kê ra để tương lai khỏi "vẽ rắn thêm chân":

- **Không** xây parser code biến prose→layout. Claude là tầng NL; code chỉ thực thi tất định. (Đã chốt
  trước đó; ghi lại để khỏi tái phát.)
- **Không** tạo "framework skill" / lớp trừu tượng chung giữa 2 skill. D4 cấm skill-gọi-skill; cố lách =
  phức tạp vô ích. Ghép qua format file (P5) là đủ.
- **Không** ép mọi thứ vào 1 skill "đa năng" (D8 phản đối; P2 routing loãng).
- **Không** đổi tên `reference/`→`references/` — doc thực tế dùng `reference/` **số ít**; đổi sang số nhiều là SAI + churn path.
- **Không** thêm config/abstraction "phòng xa". Chỉ tách config khi có ≥2 nơi dùng thật (quy tắc rule-of-three).
- **Giữ Tầng 3 (sắp lại thư mục) là tùy chọn** — vì nó bắt sửa path nội bộ mọi script (churn cao) đổi lấy
  lợi ích cosmetic. Chỉ làm khi đã quyết đóng gói plugin.

---

## 6. Đã kiểm với doc (2026-06-22) + còn ngỏ

**Đã xác minh:**
- **Plugin KHÔNG chia sẻ engine sạch được.** `${CLAUDE_PLUGIN_ROOT}` **NOT FOUND** (skills.md + plugins.md);
  `${CLAUDE_SKILL_DIR}` = *"the skill's subdirectory within the plugin, **not the plugin root**"*. → không có
  đường cho skill với tới engine cấp plugin-root. Cái có: `bin/` = *"executables added to the Bash tool's
  PATH while the plugin is enabled"* (chỉ executable). → Lựa chọn thực khi đóng gói: (a) bọc engine thành
  executable trong `bin/`; (b) vẫn nhân đôi engine mỗi skill nhưng đóng chung 1 plugin. **Plugin ≠ giải DRY engine.**
- **Cap 1.536 ký tự** cho `description`+`when_to_use` trong listing: [DOC] xác nhận (skills.md), **cấu hình được**
  (`maxSkillDescriptionChars`).

**Còn ngỏ (chưa fetch):**
- `plugins-reference` chưa đọc — có thể còn biến/cơ chế chia-sẻ khác.
- Con số token (~100 metadata / <5000 SKILL.md / 25k post-compaction): research pass, **chưa thấy nguồn verbatim**.

---

## 7. Nguồn [DOC]

1. Claude Code — Skills: https://code.claude.com/docs/en/skills.md
2. Skills frontmatter / substitutions / where-skills-live: cùng trang, các mục `#frontmatter-reference`, `#available-string-substitutions`, `#where-skills-live`
3. Agent Skills best practices (progressive disclosure, size, concision): https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
4. Agent Skills open spec: https://agentskills.io/specification
5. Sub-agents & skill preloading: https://code.claude.com/docs/en/sub-agents.md
6. Plugins: https://code.claude.com/docs/en/plugins.md

*Thu thập qua research pass 2026-06-22. [INFER] là suy luận của tác giả tài liệu này, không phải tài liệu chính thức — đọc kèm chuỗi lý do và bác nếu thấy sai.*
