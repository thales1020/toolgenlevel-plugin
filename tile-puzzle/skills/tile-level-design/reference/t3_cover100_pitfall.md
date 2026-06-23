---
name: T3 hybrid trên layouts cover100 cao = chậm 500x với find_hybrid_fast.py
description: Khi user yêu cầu T3 (easy top + trap bottom) trên layout có cover100 cao (>70%), KHÔNG dùng find_hybrid_fast.py (random pool). Phải dùng cascade hoặc bridge variant.
type: feedback
originSessionId: 5bf952b0-04ed-42f3-9813-354182a6e8fb
---
**Bài học**: `find_hybrid_fast.py` (random pool assignment) **không phù hợp** với layouts có cover100 cao.

**Bằng chứng** (benchmark 5 levels score 30-60, sequential):
- L31 (cover100=90%, strategy=Random) + `find_trap_fast.py` (T1): **4.8s**
- L32 (cover100=86%, strategy=Priority) + `find_hybrid_fast.py` (T3): **2453s (40 phút!)** = 510x chậm hơn

**Tại sao chậm**:
1. Cover100 cao = ít cells visible → easy types đặt ngẫu nhiên hay rơi vào cells ẩn = vô nghĩa
2. Random pool không kiểm soát được phân bố theo layer
3. v3 unsolvable rate cao do random distribution không pass solvability check
4. Mỗi worker tốn ~8 phút sequential

**Fix khi user yêu cầu T3 + cover100 cao**:

| Layout cover100 | Strategy | Script |
|---|---|---|
| <50% (pickable trải nhiều layers) | Priority | `find_hybrid_priority_v2.py` |
| 50-70% (mid cover) | Random / Priority | `find_hybrid_fast.py` (OK) |
| **>70% (deep uniform)** | **Cascade hoặc Bridge** | `find_hybrid_cascade_L21.py` / `find_bridge_L21.py` |
| **>80% (rất nhiều cover100)** | **Bridge / Guided** | `find_bridge_L21.py` / `find_guided_trap_L21.py` |

**Rule mới (workflow)**:
1. User yêu cầu T3 + layout → check `layout_strategy_analysis.csv`
2. Nếu **cover100 > 70%** → KHÔNG dùng `find_hybrid_fast.py`
3. Dùng cascade/bridge/guided thay (đã optimize cho deep layouts)
4. Nếu layout không phải L21 (chưa có script chuyên) → cảnh báo user, đề xuất L21 hoặc dùng T1 thay

**Why:** User mất 40 phút chờ vì script không phù hợp. Phải warn trước khi launch nếu predict sẽ chậm.

**How to apply**: Trước khi launch T3 search, check cover100% của layout. Nếu >70% và không có script chuyên cho layout đó → đề xuất alternative (đổi layout, đổi pattern, hoặc dùng T1 thay).
