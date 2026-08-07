---
name: winrate-target
description: "Thiet ke / tao level Tile Pyramid theo CHI SO NGUOI CHOI THUC (win_rate, thoi luong, revive, booster) o tung giai doan early/mid/late — dua tren model hoc tu 56K luot choi + 9 playlog. Giai bai toan: 'tao level voi layout [X] co chi so [Y] la [Z] o giai doan [early/mid/late]'. Ca 2 chieu: XUOI (do 1 layout ra 5 chi so) va NGUOC (sinh layout dat chi so muc tieu). Khac gen-layout/tile-level-design: cac skill do cham DO KHO TINH (diffScore) cua ban co; skill nay cham HANH VI NGUOI CHOI THAT theo vi tri man."
when_to_use: "Khi nguoi dung muon tao/thiet ke level nham mot CHI SO NGUOI CHOI cu the: win_rate (ty le thang), thoi luong choi, ty le revive, ty le dung booster — dac biet co kem GIAI DOAN (early/mid/late) hoac vi tri man. Vi du: 'tao level layout doi xung co win_rate dot 1 la 87% o late', 'layout 54 dat Win/Att 70% o mid', 'man nay o vi tri 180 thi bao nhieu % thang'. KHONG dung khi chi can do kho tinh/diffScore (dung tile-level-design) hoac tao hinh tu anh (dung gen-layout). Skill nay CHAY SAU khi da co hinh, hoac tu sinh hinh kim tu thap doi xung."
---

# Skill winrate-target — thiết kế level theo chỉ số người chơi thật

Giải trực tiếp đề bài: **"Tạo level với layout [X] có chỉ số [Y] là [Z] ở giai đoạn [M: early/mid/late] cho trình độ [N]"**.

Prompt chuẩn 5 ô: **X** = hình/layout · **Y** = chỉ số · **Z** = giá trị đích · **M** = giai đoạn · **N** = trình độ người chơi (tuỳ chọn — bỏ trống thì tính cho **người chơi trung bình của dân số**, đúng như trước khi có N).

Khác 3 skill kia của plugin: chúng chấm **độ khó TĨNH của bàn cờ** (diffScore/final_score). Skill này chấm **hành vi NGƯỜI CHƠI THẬT** — và biết cùng bàn cờ ở `late` dễ hơn `early` (dân giỏi lên).

## 0. LUÔN chạy bằng file trong skill này

```bash
cd <skill>/winrate-target
python winrate_tool.py <lệnh>
```
Model + artifact nằm sẵn trong `analysis/`. Engine mượn từ skill `gen-layout` (tự tìm `../gen-layout/engine`).

## 0b. ⚠️ BẮT BUỘC — thuật lại cảnh báo trôi model

Mọi lệnh `winrate_tool.py` in một dòng trạng thái ở **đầu output**. Đây là cơ chế cảnh báo duy
nhất (skill không có popup). **Không được bỏ qua hay tóm tắt mất nó.**

| Trạng thái | Nghĩa | Bạn PHẢI làm gì |
|---|---|---|
| `[!!] CANH BAO ... DA TROI` | ≥2 cohort vượt ngưỡng **3,5 điểm MAE**, hoặc một cohort lệch >7 điểm | **Nêu ngay ở đầu câu trả lời**, kèm cohort nào lệch bao nhiêu. Vẫn đưa kết quả, nhưng nói rõ nó phản ánh **dân số cũ**. Gợi ý hiệu chuẩn lại. |
| `[~] troi nhe` | Có dấu hiệu, chưa vượt ngưỡng | Nhắc một câu, không cần nhấn mạnh. |
| `[OK] Model con dung` | Đã kiểm, dưới ngưỡng | Có thể nói ngắn gọn là model còn hợp lệ. |
| `[i] CHUA kiem tra troi bao gio` | Chưa ai chạy kiểm | Nói rõ **độ tin cậy chưa được kiểm chứng trên dân số hiện tại**. |

**Luôn kèm ±MAE khi báo bất kỳ con số dự báo nào** — lấy từ `M["MAE_STAGE_CV"]` (kiểm định chéo,
trung thực hơn `MAE_STAGE` vốn là in-sample).

## 0c. Kiểm tra trôi & hiệu chuẩn lại

```bash
# Đo trôi mà KHÔNG đổi model (an toàn, chạy bất cứ lúc nào):
python scripts/eval_cohort.py <csv cohort mới> ... --check-drift --quiet
python scripts/eval_cohort.py ... --check-drift --threshold 5   # nới nếu báo quá nhiều

# Chỉ hiệu chuẩn lại khi cảnh báo WARN — xem trước rồi mới ghi:
python scripts/recalibrate.py <csv> --cohort <tên> --dry-run
python scripts/recalibrate.py <csv> --cohort <tên>
```

**KỶ LUẬT QUAN TRỌNG — đừng hiệu chuẩn tuỳ tiện.** β (Tầng 1) là **cây thước**: nó đo độ khó bàn
cờ bằng hình học + bot mô phỏng, **không bao giờ được refit**, nên mọi thiết kế đều so được với
nhau. Cái được hiệu chuẩn lại là θ (trình độ dân số) và Tầng 3 (bảng quy đổi) — chúng **phải** đổi
khi tệp người chơi đổi.

Nhưng: **KHÔNG hiệu chuẩn lại cho từng A/B test riêng lẻ.** Nếu test A đo bằng model A, test B đo
bằng model B thì **không so A với B được nữa**. Giữ một model tham chiếu cho cả chu kỳ; dùng
`eval_cohort.py` để *phát hiện* trôi mà không đổi gì; chỉ hiệu chuẩn khi dân số thực sự đã đổi
(ví dụ sang bản build mới). Mỗi lần hiệu chuẩn đều được ghi vào `M["PROVENANCE"]`.

## 1. Chín chỉ số Y — cái nào dùng được

**KHÔNG chép số MAE vào đây** (tài liệu sẽ lệch ngay lần hiệu chuẩn kế tiếp). Lấy số sống bằng:

```bash
python winrate_tool.py info      # in PROVENANCE + MAE in-sample/CV cho cả 9 chỉ số
```

| Chỉ số Y | Đo | Sinh | Dùng để |
|---|---|---|---|
| **win_rate** (1stAtt Win %) | ✅ | ✅ | ĐỘ KHÓ — **tin nhất, tốt ở cả 3 giai đoạn** |
| **thoi_luong** (phút) | ✅ | ✅ | nhịp game |
| **near_miss** (%) | ✅ | ✅ | cơ hội IAP — sai số rất thấp |
| **undo / shuffle / magnet** (%) | ✅ | ✅ | tách nhỏ booster; tốt ở early/mid |
| **booster** (%) | ✅ | ✅ | tỉ lệ dùng vật phẩm — ⚠️ **late còn yếu** |
| **revive** (%) | ✅ | ✅ | tỉ lệ dùng hồi sinh — ⚠️ **late còn yếu** |
| **win_att** (Win/Att %) | ⚠️ | ✅ | chỉ số prompt gốc — bị whale-cày làm bẩn |

- **win_rate = win_rate_at_att_1** (thắng ngay lượt đầu) — sạch, mỗi người 1 phiếu.
  **Nên đặt mục tiêu bằng cái này.**
- **win_att = win_rate_per_att_pct** (Win/Att) — chỉ số prompt gốc, NHƯNG bị whale-cày làm bẩn
  (trần lý thuyết ~8.1). Sinh được nhưng mục tiêu mờ → ưu tiên `win_rate`.
- ⚠️ **`booster`/`revive` là TỈ LỆ SỬ DỤNG vật phẩm, KHÔNG phải doanh thu.** Log không có cột mua
  hàng (IAP) nào, nên tool **không dự báo được tiền**. Ở `early`, 81% người chơi *có* booster trong
  túi mà chỉ 12,7% dùng — phần lớn không phải mua.
- Nhóm này ở **`late`** sai số còn lớn → **chưa dùng để ra quyết định tiền bạc**; luôn báo kèm ±MAE.
- **Trước khi đặt mục tiêu, xem vùng khả thi** — tra bằng chính tool, không cần file ngoài:
  ```bash
  python winrate_tool.py target <Z> <stage> <metric>   # cần beta bao nhiêu, có khả thi không
  ```
  Ngoài phân bố dữ liệu thật thì `gen` sẽ báo `KHONG DAT MUC TIEU` — đó là **cơ chế chống ngoại
  suy có chủ đích**, không phải lỗi. *(Project Skylink còn có dashboard
  `data-v2/metric_coverage.html` để kéo thử trực quan — chỉ có trong repo nội bộ, không thuộc plugin.)*
- **revive** ở `early` có thể bão hoà (board nhỏ khó đủ độ khó) → tool tự báo "KHÔNG ĐẠT".

## 2. Chiều NGƯỢC — sinh layout đạt chỉ số (bài toán chính)

```bash
# X = hình đối xứng sinh mới, Y = win_rate, Z = 87%, late:
python winrate_tool.py gen win_rate 87 late sym

# X = giữ hình layout 54 có sẵn, Y = Win/Att, Z = 70%, mid:
python winrate_tool.py gen win_att 70 mid --layout 54

# thêm ô N — win_rate 82% late CHO CAO THỦ:
python winrate_tool.py gen win_rate 82 late --N cao_thu

# revive 20% ở mid:
python winrate_tool.py gen revive 20 mid
```
`gen <metric> <value> <stage> [sym] [--layout K] [--N <bậc|percentile>]` — search CÓ PHẢN HỒI: engine gán quân → model đo → dịch vùng engine theo dấu sai số → lặp. Chặn ngoại suy (chỉ nhận layout nằm trong phân bố dữ liệu thật). Báo "KHÔNG ĐẠT" khi mục tiêu vượt trần khả thi. Xuất board ra `analysis/gen_<metric>_<value>_<stage>.json`.

## 2b. Ô N — trình độ người chơi (tuỳ chọn)

**Vì sao cần:** cùng một bàn, Z đổi theo trình độ. Board win 97% cho dân TB thì cao thủ win ~99% & chơi nhanh gấp đôi. Nên **Z vô nghĩa nếu không có N** → N gắn vào để nói rõ "đạt Z cho ai".

**Cách nhập N:** tên bậc `ga`/`duoi_tb`/`tb`/`kha`/`gioi`(=`cao_thu`)/`master`, **hoặc** số percentile 0-100. Bỏ trống ⇒ **rollback**: tính cho cả phân bố dân số (E[sigmoid]), y hệt hành vi cũ.

**Nguồn N:** không cào thêm dữ liệu — dùng luôn **phân phối theta thật của hàng nghìn người chơi** đã fit sẵn trong `winrate_model.json` (7.5k–24.8k người/giai đoạn). N = chọn 1 điểm percentile trên phân phối đó.

**GIỚI HẠN TRUNG THỰC:** N **chỉ tác dụng với `win_rate` và `win_att`** (2 đầu sigmoid có theta). `thoi_luong`/`revive`/`booster` là hồi quy **phẳng, chưa có theta** → N bị **bỏ qua** (tool in cảnh báo). Muốn N cho 3 cột này cần thêm dữ liệu playtest theo độ khó để fit đường theta (đang thu qua 10 bàn CAL).

**Phân loại 1 người chơi thật** (từ playlog): `estimate_theta_from_results([(beta_màn, thắng0/1), ...])` — MLE 1 tham số. Nếu **toàn thắng/toàn thua** thì trả **CẬN** chứ không bịa số (đúng lý thuyết Rasch "complete separation"); cần ≥1 màn ngược kết quả mới chốt được điểm theta. Đây là lý do 10 bàn CAL trải β −0.86→+2.22: để có cơ hội thua ở đầu khó mà ghim theta.

## 3. Chiều XUÔI — đo 1 layout ra 5 chỉ số

```python
import winrate_tool as W
out = W.predict(board_json, engine_feats, level_pos)
# -> beta, win_rate_dot1_pct, thoi_luong_phut, revive_user_pct, booster_pct, win_att_pct, sai_so
```
`engine_feats` = dict có `intra_group, cover100, n_types, is_mystery, layerCount, tileCount` (lấy từ score của skill tile-level-design/gen-layout).

## 4. Bài toán ngược chỉ-độ-khó

```bash
python winrate_tool.py target 87 late               # win_rate 87% late -> cần beta?
python winrate_tool.py target 70 mid win_att        # Win/Att 70% mid -> cần beta?
python winrate_tool.py target 82 late win_rate --N cao_thu   # ... cho cao thủ (beta cao hơn)
```

## 5. Quy trình khép với các skill khác

1. `gen-layout` tạo HÌNH (nếu cần hình từ ảnh/chữ) →
2. skill này `gen` gán quân + độ khó để đạt chỉ số người chơi →
3. `display-json-level` render HTML chơi thử board ở `analysis/gen_*.json`.

## 6. Ranh giới trung thực (đọc trước khi báo cáo)

- **Con số `gen` báo "lệch 0.1" là model tự chấm model** — sai số THẬT vẫn là ±MAE (chạy `info`). Luôn kèm ±.
- **Win/Att sàn 8.1**: đo cả whale-cày, không phải chỉ layout. Ưu tiên `win_rate` (1stAtt).
- **6 tier designer chồng chéo** (std trong-tier 6.9 > khoảng cách 3-4) — với MAE `win_rate` hiện tại
  (xem `info`) chỉ tách được ~3-4 bậc thô, KHÔNG tách được 6 tier.
- **Có "độ khó bẫy" chưa mô hình được**: Tầng 1 (β) chỉ giải thích ~56% biến thiên độ khó thật, nên
  vẫn có level model đoán dễ hơn thực tế. **Luôn chơi thử trước khi phát hành.**
- **Bot mô phỏng không thay được playtest.** Bot dùng để trích đặc trưng thì tốt, nhưng tương quan
  giữa "bot thắng" và "người thật thắng" chỉ ~0,16 — đừng đọc "bot thắng 0%" thành "bàn bất khả thi".
- **Ô `[N]` (trình độ) chỉ tác dụng với `win_rate`/`win_att`/`near_miss`** — 6 đầu linear bỏ qua nó.
- **Tầng 1 (β) cố ý KHÔNG bao giờ được hiệu chuẩn lại** — đó là cây thước giữ cho các thiết kế so
  sánh được với nhau qua các cohort. Chỉ θ và Tầng 3 được refit.
- **Ngoài L790 là ngoại suy** — model chỉ hiệu chuẩn trên các level có đủ lượt chơi thật.
