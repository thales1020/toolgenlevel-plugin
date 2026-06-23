# Tile Explorer Level Design — Complete Guide

Tổng hợp toàn bộ kiến thức về **patterns**, **strategies**, và **speed optimization** cho việc tạo level trong Tile Explorer simulator.

---

## PART 1: PATTERNS & STRATEGIES

### 1.1 Bốn Final Patterns

Đây là các pattern thực sự khác biệt về thiết kế (output cho user):

| # | Pattern | Mục tiêu | Identifying phrase |
|---|---|---|---|
| **T1** | **Trap ẩn / 90% fail** | Có lời giải nhưng 90-100% greedy thua → cần booster | "trap ẩn / cần booster / 90% thua" |
| **T2** | **Top N layers dễ** | Top dễ rõ ràng, bottom diversify | "top dễ / layer đầu dễ" |
| **T3** | **Easy top + trap bottom** | Hybrid với chuyển tiếp rõ ràng | "dễ đầu khó cuối / easy start hard finish" |
| **T4** | **Clear 50% rồi bí** | Greedy clear 40-60% rồi gặp trap | "clear 50% rồi bí / giải được nửa rồi kẹt" |

> Note: Có 1 pattern phụ **T5 Guided Trap** (breadcrumbs + cascade) — chiến lược tăng cường cho T3/T4 trên layouts có nhiều cover100.

### 1.2 Bảy chiến lược tile assignment

Chiến lược chọn cách phân bố tile để tạo ra pattern:

| Strategy | Logic | Layout phù hợp |
|---|---|---|
| **TEEngine** | Generator gốc + tuning knobs (distance, top3_easy, ...) | Mọi layout |
| **TEEngine + window** | Top3_easy=True + window metric ≥ 0.60 | Tile count thấp (7-13) |
| **Custom Random** | Shuffle pools per half (top easy / bottom trap) | Layout đơn giản |
| **Custom Priority** | Easy types **chỉ trên pickable cells**, tránh cover100 | Pickable trải 2+ layers (74 layouts) |
| **Custom Cascade** | Same easy type **vertical stacks** → reveal waterfall | Top-only pickable + deep uniform (19 layouts) |
| **Custom Bridge** | 3 type groups (easy / bridge / trap), bridge spans top→bottom | Cover100 cao |
| **Custom Guided Trap** | 3-zone gradient (easy / breadcrumbs / trap cascade) | Cover100 cao + muốn fair-challenge |

### 1.3 Chín template scripts

Mapping cụ thể giữa pattern × strategy → script:

| # | Script | Pattern | Strategy | Any layout | Tốc độ |
|---|---|---|---|---|---|
| 1 | `find_trap_fast.py` | T1/T4 | TEEngine + greedy fail | ✓ | 1-10s |
| 2 | `find_easy_first_half.py` | T2 | TEEngine + window | ✓ | ~30s |
| 3 | `find_hybrid_fast.py` | T3 | Custom Random | ✓ | 5-30s |
| 4 | `find_hybrid_priority_v2.py` | T3 | Custom Priority | L20-style | ~8s |
| 5 | `find_hybrid_cascade_L21.py` | T3 | Custom Cascade | L21-style | ~2s |
| 6 | `find_bridge_L21.py` | T3 | Custom Bridge | L21 | 5-10s |
| 7 | `find_bridge_hard_L21.py` | T3 | Bridge hard variant | L21 | ~17min |
| 8 | `find_guided_trap_L21.py` | T5 | Guided Trap | L21 | <1s |
| 9 | `find_clear50_trap.py` ⭐ | T4 | **Auto-strategy** | ✓ | 5-30s |
| 10 | `gen_all_9.py` ⭐ | All 9 | Parallel batch | Mixed | **~20s** |

### 1.4 Bảng quyết định: Pattern × Layout → Script

```
Pattern (T1-T4)
  ↓
Layout structure:
  ├── Pickable trải 2+ layers (74 layouts: L20, L25, L70, L107)
  │     → TEEngine, Random, Priority
  ├── Top-only pickable + deep uniform (19 layouts: L21, L46, L98)
  │     → Cascade, Bridge, Guided Trap (cần "tools" cho cover100)
  └── Single pickable layer, không stacks (24 layouts: L10, L38)
        → TEEngine, Random
```

**Reference**: `layout_strategy_analysis.csv` — 117 layouts đã classify.

### 1.5 Bảng tổng hợp Pattern × Strategy

| Template | Strategy | Layout | Script |
|---|---|---|---|
| **T1 Trap ẩn** | TEEngine + greedy fail | Any | `find_trap_fast.py` |
| **T2 Top dễ** | TEEngine + window | Tile count thấp | `find_easy_first_half.py` |
| | Custom Priority | Pickable nhiều layers | `find_hybrid_priority_v2.py` |
| | Custom Cascade | Top-only + deep | `find_hybrid_cascade_L21.py` |
| **T3 Easy top + trap** | Custom Random | Any | `find_hybrid_fast.py` |
| | Custom Priority | L20, L25 | `find_hybrid_priority_v2.py` |
| | Custom Cascade | L21, L46 | `find_hybrid_cascade_L21.py` |
| | Custom Bridge easy | Cover100 cao, muốn rescue L1 | `find_bridge_L21.py` |
| | Custom Bridge hard | Cover100 cao, khó tối đa | `find_bridge_hard_L21.py` |
| | Custom Guided Trap | Cover100 cao, fair-challenge | `find_guided_trap_L21.py` |
| **T4 Clear 50%** | Auto-strategy | Any | `find_clear50_trap.py` ⭐ |
| | Custom Cascade | L21 | `find_hybrid_cascade_L21.py` |
| | Custom Bridge | L21 | `find_bridge_L21.py` |
| | Custom Guided Trap | L21 | `find_guided_trap_L21.py` |

### 1.6 Math cho Custom Assignment

Công thức partition: `x types × 6 + y types × 3 = total_cells`

Suy ra: `3x = total_cells - 3 × (x+y)`

| Layout | Cells | Top | Bot | Partition example |
|---|---|---|---|---|
| L20 | 72 | 36 | 36 | 7×6 + 10×3 = 72 (17 types) |
| L21 | 66 | 27 | 39 | 4×6 + 14×3 = 66 (18 types) |
| L25 | 75 | 20 | 55 | 8×6 + 9×3 = 75 (17 types) |
| L74 | 69 | 18 | 51 | 6×6 + 11×3 = 69 (17 types) |

### 1.7 Bridge Distribution chi tiết

**Bridge** = 6 copies/type, spans top→bottom, player nhận diện ở cả 2 đầu.

| Variant | Bridge types | L1 copies | L3 content | Score |
|---|---|---|---|---|
| **Easy** | 4 | 3/type (match ngay L1) | Easy + bridge | ~71 |
| **Harder** | 4 | 2/type (cần L0 thứ 3) | Easy + bridge | ~67 |
| **Hard** | 2 | 1/type (rải xa) | Hard_mid trap | ~58 |

**Critical rules**:
1. Bridge phải **span cả top VÀ bottom** — không cluster ở middle
2. Bridge phải form **matchable triples** ở bottom (≥2 pickable sau khi clear top)
3. Top layers phải có **≥2 instant triples** ngay từ đầu
4. Bridge copies **càng cách xa càng khó**

### 1.8 Guided Trap chi tiết

**3 zones**:
```
Zone 1 (top):    Easy cascade — instant triples
Zone 2 (mid):    Easy + BREADCRUMBS (1 copy mỗi trap type, partial visible)
Zone 3 (bottom): Trap CASCADE (same type stacked vertical)
```

**Khác bridge**: bridge **lặp lại** nhiều copies (player match được). Breadcrumbs **chỉ 1 copy** (player chỉ biết type tồn tại, không match được).

**Khi dùng**: muốn level **fair-challenge** — khó nhưng player có thông tin để decide thay vì đoán mò.

### 1.9 Booster mechanics (đã modify)

**Shuffle** — dynamic triple count + tray priority:
1. Tray ≥3 distinct types → force up to **3 triples**; otherwise **2**
2. **Absolute tray priority**: types đã có trên tray (2>1) > types chưa có
3. Smart force: chỉ force `3 - on_tray` copies (type 2 trên tray → force 1)
4. Relaxed candidate filter: `board_copies >= 3 - on_tray`

**Undo** — trả **1 tile** cuối từ tray về board (3 uses).

**+1 Slot** — tray 7→8, one-time.

**Restart fix**: `_original_tile_ids` saved at init.

---

## PART 2: SPEED OPTIMIZATION

### 2.1 Filter order (cheap → expensive)

```
1. type_count check        ~0ms        (set comparison)
2. instant_triples check   ~0ms        (count pickable types)
3. score check             ~1ms        (DifficultyScorer)
4. v3 solvable             ~10-500ms   (use 100k cap)
5. greedy 30 quick reject  ~50-200ms   (2-stage greedy stage 1)
6. greedy 300 full         ~500-2000ms (only on promising)
7. solve_path double-verify ~100-3000ms (final check)
```

**Quy tắc**: NEVER chạy v3 trước khi check tile_count + score.

### 2.2 Precompute & cache (layout-only data)

| Cái gì | Tại sao | Speedup |
|---|---|---|
| `bb[]` blocking bitmask | Layout-only, không đổi với tile_ids | Tránh O(n²) mỗi iteration |
| Template board | `load_board_from_file()` đọc disk mỗi lần | I/O 100ms → 0ms |
| Cell positions array | Build Board từ array nhanh hơn JSON parse | 10x |
| `cascade_chains` | Layout-only | Compute 1 lần |
| `tier1` (pickable cells) | Layout-only | Compute 1 lần |

### 2.3 2-stage greedy

```python
# Stage 1: 30-50 runs quick reject
fr_quick, _ = greedy(tile_ids, 30)
if fr_quick < 0.5: continue  # 80%+ candidates rejected

# Stage 2: 300 runs full (only on promising)
fr_full, avg_clr = greedy(tile_ids, 300)
```

**Speedup**: 5-10x.

### 2.4 v3 cap optimization

```python
# Trước (chậm): 500ms-2s mỗi unsolvable
solve_v3(board, max_expansions=2_000_000)

# Sau (nhanh): solvable boards thường <50k
solve_v3(board, max_expansions=100_000)
```

90% solvable boards giải trong <50k expansions.

### 2.5 Clone in-memory (không reload disk)

```python
# Trước: 1130s cho find_hybrid_custom.py
for attempt:
    board = load_board_from_file(path)  # disk I/O mỗi lần

# Sau: 0.5s (2260x speedup!)
template = load_board_from_file(path)
positions = [(c.x, c.y, c.layer_idx) for c in template.all_cells()]
def clone_board(tile_ids):
    board = Board()
    # build from cached positions
    return board
```

### 2.6 TEEngine settings

```python
eng = TEEngine()
eng.validate = False  # Skip 10-retry internal validator
```

`validate=False` skip stock solver check → 2-5x nhanh hơn.

### 2.7 Parallel execution

#### 8 workers (single pattern)

```bash
for seed in 1 11 23 47 101 239 991 1001; do
    python find_*.py $seed > log_$seed.log 2>&1 &
done
```

Seeds spread RNG, unique output `*_s{seed}.json` tránh race condition.

#### Multi-pattern parallel (`gen_all_9.py`)

```python
# 7 external scripts via subprocess.Popen
procs = [subprocess.Popen(cmd, ...) for cmd in SCRIPTS]

# 2 fastest inline (P2, P8) — tận dụng wait time
gen_p2()
gen_p8()

# Wait all
for p in procs: p.wait()
```

**Result**: 9 patterns trong **~20s** (vs 30 phút sequential = 90x speedup).

### 2.8 Bug avoidance (sai = gen lại)

| Bug | Fix |
|---|---|
| Race condition trên `candidate.json` | Unique file per worker: `*_s{seed}.json` |
| Worker overwrite trước play | Save unique file **trước** khi play_level |
| Greedy emit "solution" thực ra thua | Game-over: `len(tray) >= 7 AND no triple` (NOT `> 7`) |
| Atomic triple hit game-over giữa chừng | Check `cur_tsize + (needed-1) < TRAY_SIZE` |
| Display labels sai | Always convert `tile_id + 1` cho UI |

### 2.9 Benchmark thực tế

| Script | Trước fix | Sau fix | Speedup |
|---|---|---|---|
| `find_hybrid_custom.py` | 1130s | **0.5s** | **2260x** |
| `gen_5_patterns.py` P1+P4 | 60s/cái | **6s/cái** | **5x** |
| 9 templates sequential | 30 phút | **~95s** | **18x** |
| **9 templates parallel** | 30 phút | **~20s** | **90x** |

### 2.10 Decision tree

```
1 pattern, 1 layout       → 1 script + 8 workers          → 1-30s
1 pattern, mọi layout      → find_clear50_trap.py + auto    → 5-30s
Nhiều patterns / demo     → gen_all_9.py                   → ~20s
Sweep min/max all layouts → difficulty_minmax_combined.py  → ~21min (one-time)
```

### 2.11 Khi nào KHÔNG tăng tốc được

- **Custom v3 pass rate ~3%** (vs TEEngine 0.2%) — đã max
- **Greedy 300 runs là minimum** cho fail_rate đáng tin
- **Bridge hard** (2 types × 1/layer + fail ≥ 95%) inherent slow → ~17 phút

### 2.12 Checklist cho new search script

- [ ] Precompute `bb[]` ngoài loop
- [ ] Cache template board + positions
- [ ] `eng.validate = False`
- [ ] Filter order: types → score → v3(100k) → greedy(30) → greedy(300)
- [ ] 2-stage greedy
- [ ] Unique output file per seed
- [ ] Save unique JSON trước play
- [ ] Game-over check `>= 7 AND no triple`

---

## PART 3: REFERENCE FILES

### CSV files

| File | Nội dung | Dùng khi |
|---|---|---|
| `difficulty_minmax.csv` | TEEngine min/max per (layout, tile_count) | Tra cứu range TEEngine |
| `difficulty_minmax_custom.csv` | Custom assignment min/max (wider range) | Tra cứu range Custom |
| `difficulty_minmax_combined.csv` | True min/max (both methods) | Tra cứu trước khi gen |
| `layout_strategy_analysis.csv` | 117 layouts: pickable/cover100/stacks/strategy | Chọn strategy theo layout |
| `scoring_weights.json` | X=0.3, Y=0.3, Z=0.5, K=0.6 | Verify weights |

### 9 Templates summary

```
1. find_trap_fast.py         — T1/T4 trap, any layout
2. find_easy_first_half.py   — T2 top dễ, window metric
3. find_hybrid_fast.py       — T3 random
4. find_hybrid_priority_v2.py — T3 priority (L20-style)
5. find_hybrid_cascade_L21.py — T3 cascade (L21-style)
6. find_bridge_L21.py        — T3 bridge (3 difficulty levels)
7. find_bridge_hard_L21.py   — T3 bridge hard variant
8. find_guided_trap_L21.py   — T5 guided trap
9. find_clear50_trap.py      — T4 auto-strategy ⭐
+ gen_all_9.py               — All 9 in parallel ~20s ⭐
```

### Critical game invariants (MUST follow)

1. **Game-over rule**: `len(tray) >= 7 AND no tile type has count ≥ 3`
2. **Display labels**: `tile_id + 1` (UI is 1-indexed, internal 0-indexed)
3. **Atomic triple bounds**: `cur_tsize + (needed-1) < TRAY_SIZE`
4. **Layout capacity**: `max_types = total_cells // 3`
5. **Clear `tile_id = -1`** before regeneration
6. **Use `load_board_from_path`** with absolute path

---

## QUICK REFERENCE CARD

### User says X → Do Y

| User says | Pattern | Script |
|---|---|---|
| "trap ẩn / cần booster" | T1 | `find_trap_fast.py` |
| "top dễ / easy first N" | T2 | `find_easy_first_half.py` |
| "dễ đầu khó cuối / bridge" | T3 | `find_bridge_L21.py` / `find_hybrid_fast.py` |
| "90% thua" | T1 | `find_trap_fast.py` |
| "clear 50% rồi bí" | T4 | `find_clear50_trap.py` |
| "không đoán mò / guided" | T5 | `find_guided_trap_L21.py` |
| "tạo 9 levels / demo all" | All | `gen_all_9.py` |
| "unsolvable" | - | `find_unsolvable.py` |
| "min/max sweep" | - | `difficulty_minmax_combined.py` |

### Speed cheat sheet

```
Tốc độ tối đa:
1. Precompute bb[] ngoài loop
2. validate=False
3. v3 cap = 100k
4. 2-stage greedy (30 → 300)
5. Filter order cheap → expensive
6. Clone in-memory, không reload disk
7. Unique output per worker
8. Parallel: 8 workers + Popen
9. gen_all_9.py cho batch
```
