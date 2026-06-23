---
name: 5 Level Design Patterns
description: Five proven level-design patterns — trap ẩn, easy-top-hard-bottom, hybrid custom, 90% fail, clear-50%-then-trap — with method, template, and quick-select table
type: project
originSessionId: 9cb29a82-5617-4dd8-9f97-2bb165e50048
---
## 5 Pattern thiết kế level

### Pattern 1: Level trap ẩn
- **Mục tiêu**: v3 solvable + 95-100% greedy fail. Nhìn dễ nhưng thực ra rất khó.
- **Method**: TEEngine + greedy-fail-rate metric
- **Template**: `find_l20_17.py`
- **Key**: distance thấp (0-5) dồn same-type lên top → bẫy triple dễ → dead-end. cc cao (15-19).
- **Filter**: tile count + score range + v3 solvable + 300 greedy playouts fail_rate ≥ 0.90
- **Reference**: `trap_an_L20_s82.json`

### Pattern 2: Top 3 layers dễ, bottom khó
- **Mục tiêu**: Top 3 layers nhiều triples dễ match, bottom diversity cao.
- **Method**: TEEngine + 2-adjacent-layer window metric
- **Template**: `find_easy_first_half.py`
- **Key**: `top3_easy=True` hoặc `top4_easy=True`. Window_frac ≥ 0.60.
- **Giới hạn**: tile count cao (17+) làm v3 pass rate giảm mạnh. Tốt nhất với 7-13 types.

### Pattern 3: Top dễ + trap ở bottom (custom assignment)
- **Mục tiêu**: Greedy clear top 3 layers (~40-50%), rồi chết ở bottom.
- **Method**: Custom tile assignment — bypass TEEngine hoàn toàn.
- **Template**: `find_hybrid_custom.py`
- **Key**: x types × 6 copies + y types × 3 copies = total_cells.
  - **6×6 variant**: 6 easy types × 6 copies fill top 3 entirely. Pure easy top, score ~80.7
  - **6×4 variant**: 6 easy types × 4 copies + trap cells xen top. Score ~83.5
- **Filter**: fail_rate ≥ 80%, score in range, v3 solvable
- **Why not TEEngine**: TEEngine không tạo được phân bố cực đoan (6 types chiếm 100% top layers).
- **Reference**: `L20_hybrid_easytop_s81.json` (6×6), `L20_hybrid_tight_s84.json` (6×4)

### Pattern 4: 90% cách chơi đều thua
- **Mục tiêu**: v3 solvable + greedy fail ≥ 90%.
- **Method**: TEEngine + greedy fail rate (giống pattern 1 nhưng threshold linh hoạt hơn)
- **Template**: `find_80fail.py` hoặc `find_l20_17.py`
- **Key knobs**: distance thấp (0-5), cc cao (15-22), hard_code 1-3
- **Kết quả thực tế**: L20 + 17 types → 100% candidates đều fail_rate = 100%. Rất dễ đạt với type count cao.

### Pattern 5: Clear 50-60% rồi gặp trap
- **Mục tiêu**: Greedy clear ~50-60% cells trước khi chết.
- **Method**: Custom tile assignment (giống pattern 3, điều chỉnh tỷ lệ easy/trap)
- **Template**: `find_hybrid_custom.py`
- **Key**: 
  - Clear 50%: easy types chiếm ~50% cells (6 types × 6 copies trên 6 layers)
  - Clear 60%: cần giảm tile count (12-13 types) hoặc layout nhiều layers hơn
- **Metric**: avg_cleared / total_cells trong greedy playout
- **Kết quả**: L20, 17 types, 6×6 → avg_cleared = 33/72 = 46%

## Bảng chọn nhanh

| User nói | Pattern | Method | Template |
|---|---|---|---|
| "trap ẩn / cần booster" | 1 | TEEngine + greedy fail | find_l20_17.py |
| "top dễ, bottom khó" | 2 | TEEngine + window metric | find_easy_first_half.py |
| "top dễ + trap bottom" | 3 | Custom assignment | find_hybrid_custom.py |
| "90% thua" | 4 | TEEngine + greedy fail ≥ 90% | find_80fail.py |
| "clear 50-60% rồi bí" | 5 | Custom + avg_cleared | find_hybrid_custom.py |
