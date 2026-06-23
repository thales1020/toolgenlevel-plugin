"""
Tile Explorer Level Generation Simulator v3
=============================================
RE'd from libil2cpp.so (Tile Explorer v1.77.1) via IDA Pro.

v3 fixes (from audit):
- Global board-wide tile assignment with shuffled pool
- Knobs as flags computed once, applied per-cell during binding
- Pool built with proper x3 groups + post-process x3 fixup
- Solver: tray type-grouping insertion (same-type adjacent)
- Solver: clear ALL triplets per pick (not just first)
- Solver: visibility threshold verified from IsCanPickUp (0x150D6A8)
- HardTag separated from GetTileSetIndex (matching game architecture)
"""

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except Exception:  # headless / no-Tk env: stub so the SCORER + Board still import (GUI unused).
    class _TkStub:                       # tk.Canvas / tk.Toplevel / tk.Tk -> `object` base
        def __getattr__(self, _n): return object
    tk = ttk = messagebox = filedialog = _TkStub()
import json, os, random
import tile_metadata as meta
import tile_logger as logger

# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

TILE_COLORS = [
    ("#FF6B6B", "★",  "Red"),
    ("#4ECDC4", "♥",  "Teal"),
    ("#45B7D1", "♦",  "Blue"),
    ("#96CEB4", "♣",  "Green"),
    ("#FFEAA7", "♠",  "Yellow"),
    ("#DDA0DD", "✿",  "Plum"),
    ("#FF8C42", "❀",  "Orange"),
    ("#98D8C8", "☀",  "Mint"),
    ("#C39BD3", "☂",  "Lilac"),
    ("#F7B2BD", "☃",  "Pink"),
    ("#6A89CC", "⚓",  "Indigo"),
    ("#B8E994", "⚡",  "Lime"),
    ("#FAD390", "✈",  "Sand"),
    ("#E55039", "✚",  "Coral"),
    ("#78E08F", "✪",  "Jade"),
    ("#82CCDD", "❄",  "Sky"),
    ("#EA8685", "✦",  "Rose"),
    ("#F8A5C2", "❁",  "Candy"),
    ("#786FA6", "♛",  "Violet"),
    ("#CF6A87", "♞",  "Berry"),
    ("#F5CD79", "♫",  "Gold"),
    ("#546DE5", "✓",  "Cobalt"),
    ("#63CDDA", "✶",  "Aqua"),
    ("#CAD3C8", "❖",  "Stone"),
    ("#574B90", "♨",  "Grape"),
]

LAYER_COLORS = [
    "#4A90D9", "#50C878", "#E74C3C", "#F1C40F",
    "#9B59B6", "#E67E22", "#E91E90", "#1ABC9C",
    "#8D6E63", "#607D8B", "#5DADE2", "#58D68D",
]

# Difficulty presets (from RE analysis of RemoteConfig + level progression)
DIFFICULTY_PRESETS = {
    "Tutorial (1-50)": dict(
        level_number=25, color_count=3, hard_code=0,
        less_type=False, up_easy=False, top2_easy=False,
        distance=0, val_replace=False, val_mode=0,
        style_mode=0, extended=False, binding="random",
    ),
    "Mid-game (51-100)": dict(
        level_number=75, color_count=4, hard_code=0,
        less_type=True, up_easy=True, top2_easy=False,
        distance=0, val_replace=True, val_mode=1,
        style_mode=0, extended=False, binding="random",
    ),
    "Hard (101-500)": dict(
        level_number=200, color_count=5, hard_code=1,
        less_type=True, up_easy=True, top2_easy=True,
        distance=3, val_replace=True, val_mode=1,
        style_mode=0, extended=False, binding="random",
    ),
    "Very Hard (500+)": dict(
        level_number=600, color_count=6, hard_code=2,
        less_type=True, up_easy=True, top2_easy=True,
        distance=5, val_replace=True, val_mode=2,
        style_mode=7, extended=False, binding="random",
    ),
    "Extreme (HardCode 3)": dict(
        level_number=1000, color_count=7, hard_code=3,
        less_type=True, up_easy=True, top2_easy=True,
        distance=8, val_replace=True, val_mode=3,
        style_mode=3, extended=True, binding="random",
    ),
    "Easy Preset Binding": dict(
        level_number=50, color_count=3, hard_code=0,
        less_type=False, up_easy=False, top2_easy=False,
        distance=0, val_replace=False, val_mode=0,
        style_mode=0, extended=False, binding="preset",
    ),
    "2-Color Simple": dict(
        level_number=10, color_count=2, hard_code=0,
        less_type=False, up_easy=False, top2_easy=False,
        distance=0, val_replace=False, val_mode=0,
        style_mode=0, extended=False, binding="random",
    ),
    "9-Color Max": dict(
        level_number=500, color_count=9, hard_code=3,
        less_type=True, up_easy=True, top2_easy=True,
        distance=9, val_replace=True, val_mode=1,
        style_mode=3, extended=True, binding="random",
    ),
}

# ─────────────────────────────────────────────────────────────
# DotNetRandom — port of C# System.Random for Unity compatibility
# ─────────────────────────────────────────────────────────────

class DotNetRandom:
    """
    Exact port of C# System.Random (Knuth subtractive PRNG).
    Given same seed, produces identical sequence as .NET System.Random.
    Used for strip tie-break to match Unity LayoutDifficultyAnalyzer.
    """
    MBIG = 2147483647
    MSEED = 161803398

    def __init__(self, seed=0):
        mj = self.MSEED - abs(seed)
        self._seed_array = [0] * 56
        self._seed_array[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            self._seed_array[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += self.MBIG
            mj = self._seed_array[ii]
        for k in range(1, 5):
            for i in range(1, 56):
                self._seed_array[i] -= self._seed_array[1 + (i + 30) % 55]
                if self._seed_array[i] < 0:
                    self._seed_array[i] += self.MBIG
        self._inext = 0
        self._inextp = 21

    def _internal_sample(self):
        inext = self._inext + 1
        if inext >= 56: inext = 1
        inextp = self._inextp + 1
        if inextp >= 56: inextp = 1
        retval = self._seed_array[inext] - self._seed_array[inextp]
        if retval < 0:
            retval += self.MBIG
        self._seed_array[inext] = retval
        self._inext = inext
        self._inextp = inextp
        return retval

    def next(self, max_value=None):
        """Same as C# Random.Next(maxValue)."""
        if max_value is None:
            return self._internal_sample()
        return int(self._internal_sample() * (1.0 / self.MBIG) * max_value)


# ─────────────────────────────────────────────────────────────
# Scoring Weights — persistence
# ─────────────────────────────────────────────────────────────

SCORING_WEIGHTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scoring_weights.json")
DEFAULT_SCORING_WEIGHTS = {"X": 1.0, "Y": 1.0, "Z": 1.0, "K": 1.0}


def load_scoring_weights() -> dict:
    try:
        with open(SCORING_WEIGHTS_FILE, "r") as f:
            w = json.load(f)
        for k in DEFAULT_SCORING_WEIGHTS:
            if k not in w:
                w[k] = DEFAULT_SCORING_WEIGHTS[k]
        return w
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_SCORING_WEIGHTS)


def save_scoring_weights(weights: dict):
    try:
        with open(SCORING_WEIGHTS_FILE, "w") as f:
            json.dump(weights, f, indent=2)
    except OSError:
        pass


# ─────────────────────────────────────────────────────────────
# Data Model
# ─────────────────────────────────────────────────────────────

class Cell:
    __slots__ = ("x", "y", "tile_id", "layer_idx")
    def __init__(self, x, y, layer_idx=0):
        self.x = x; self.y = y; self.tile_id = -1; self.layer_idx = layer_idx


class Layer:
    def __init__(self, lid=0):
        self.id = lid; self.cells: list[Cell] = []
    def add(self, x, y):
        if not any(c.x == x and c.y == y for c in self.cells):
            c = Cell(x, y, self.id); self.cells.append(c); return c


class Board:
    def __init__(self, name=""):
        self.name = name; self.layers: list[Layer] = []
    def total_cells(self): return sum(len(l.cells) for l in self.layers)
    def all_cells(self): return [c for l in self.layers for c in l.cells]
    def clear_tiles(self):
        for c in self.all_cells(): c.tile_id = -1


# ─────────────────────────────────────────────────────────────
# Level Generation Engine (v3 — audit-fixed)
# ─────────────────────────────────────────────────────────────

class TEEngine:
    """
    Tile Explorer level generation — v3 (post-audit fixes).

    Fix #1: ContainsValue check — track used ICON VALUES, not positions
    Fix #2: Pool always advances, slot only on assign or special-skip
    Fix #3: Knobs as flags checked DURING binding, not modifying pool
    Fix #4: Pool built from simulated tile set config pattern
    """

    def __init__(self):
        self.level_number = 1
        self.color_count = 4
        self.hard_code = 0          # 0-3
        self.less_type = False      # Knob 1: field_312
        self.up_easy = False        # Knob 2: field_359 (top 1 layer)
        self.top2_easy = False      # Knob 4: field_460 (top 2 layers)
        self.top3_easy = False      # Extended: top 3 layers
        self.top4_easy = False      # Extended: top 4 layers
        self.distance = 0           # Knob 3: field_372 (level 101+)
        self.val_replace = False    # Knob 5: field_612
        self.val_mode = 0           # field_616 (0-3)
        self.style_mode = 0         # RemoteConfig offset 176
        self.extended = False       # RemoteConfig offset 504
        self.binding = "random"
        self.hard_bg_count = 0
        self.validate = True
        self.custom_triples = None  # dict[int, int] | None — tile_type → triple_count

    def get_tile_set_index(self) -> tuple[int, int]:
        """
        GetTileSetIndex (0x15055A8) — EXTENDED for GD flexibility.

        Returns (tile_set_index, effective_color_count).

        Original Unity game supports max 9 colors, but this tool allows up to 25
        for experimental/event levels. For cc > 9, we use an extrapolated tile set
        index (not matching any real Unity tile set).
        """
        cc = max(2, min(25, self.color_count))
        if cc <= 5:
            return (71 + cc, cc)          # Standard 2-5 colors
        if cc <= 6:
            return (75 + cc, cc)          # Enhanced 6 colors
        if cc <= 9:
            return (27 + cc, cc)          # Extended 7-9 colors
        # cc 10-25: extrapolated (not in Unity, tool-only)
        return (100 + cc, cc)

    def _get_effective_cc(self) -> int:
        """Apply HardTag modifier to color count (separate from tile set)."""
        _, base_cc = self.get_tile_set_index()
        cc = base_cc
        # HardTagDescribe_SetLevelHardCode (0x15977B0)
        if self.hard_code >= 2: cc = min(cc + 1, 25)
        if self.hard_code >= 3: cc = min(cc + 1, 25)
        return cc

    def generate(self, board: Board) -> dict:
        """Full pipeline matching game's phase order."""
        board.clear_tiles()
        all_cells = board.all_cells()
        if not all_cells:
            return {"error": "empty"}

        tsi, _ = self.get_tile_set_index()
        eff_cc = self._get_effective_cc()
        n = len(all_cells)

        # --- Knobs: set flags (matching game — flags set BEFORE binding) ---
        knob_flags = self._compute_knob_flags(board, eff_cc)

        # Phase 1: Build icon pool from tile set (simulated config)
        pool = self._build_icon_pool(n, eff_cc)

        # Phase 2: HardBgTiles pre-assignment
        bg_assigned = 0
        if self.hard_bg_count > 0:
            bg_assigned = self._assign_hard_bg(all_cells)

        # Phase 3: Main tile binding
        if self.binding == "preset":
            self._bind_preset(all_cells, eff_cc, knob_flags, bg_assigned)
        else:
            self._bind_random(all_cells, pool, eff_cc, knob_flags, bg_assigned)

        # Phase 3.5: Fix x3 distribution broken by knob remapping
        self._fix_x3_distribution(all_cells, eff_cc)

        # Phase 4: TileValueReplace (level 51+)
        if self.val_replace and self.level_number >= 51:
            self._apply_value_replace(all_cells, eff_cc)
            self._fix_x3_distribution(all_cells, eff_cc)  # value replace can break x3

        # Phase 5: ThereSolution validate + retry
        solvable = True
        if self.validate:
            for attempt in range(10):
                if self._check_solution(board):
                    break
                # Retry: reshuffle + re-apply x3 fix
                board.clear_tiles()
                if self.hard_bg_count > 0:
                    self._assign_hard_bg(all_cells)
                pool2 = self._build_icon_pool(n, eff_cc)
                if self.binding == "preset":
                    self._bind_preset(all_cells, eff_cc, knob_flags)
                else:
                    self._bind_random(all_cells, pool2, eff_cc, knob_flags)
                self._fix_x3_distribution(all_cells, eff_cc)
            else:
                solvable = False

        # Collect stats
        dist = {}
        for c in all_cells:
            dist[c.tile_id] = dist.get(c.tile_id, 0) + 1

        layer_stats = {}
        for li, layer in enumerate(board.layers):
            lc = {}
            for c in layer.cells:
                lc[c.tile_id] = lc.get(c.tile_id, 0) + 1
            layer_stats[li] = {"cells": len(layer.cells), "types": len(lc), "dist": lc}

        return {
            "tile_set": tsi, "eff_cc": eff_cc,
            "total": n, "dist": dist,
            "solvable": solvable, "bg_tiles": bg_assigned,
            "layers": layer_stats,
            "multiples_of_3": all(v % 3 == 0 for v in dist.values()),
            "knobs": knob_flags,
        }

    # ── Fix #4: Pool from simulated tile set config ──

    def _build_icon_pool(self, n: int, cc: int) -> list[int]:
        """
        Build icon pool matching game's tile set config pattern.

        Game constraint: each tile type MUST appear in multiples of 3
        (you need 3 matching tiles to clear a group).

        If custom_triples is set, use GD-specified triple counts per type.
        Otherwise: n cells / 3 = total_groups, distribute groups across cc types.
        """
        # Custom triple counts (GD-specified)
        if self.custom_triples:
            pool = []
            for t in range(cc):
                triple_count = self.custom_triples.get(t, 0)
                pool.extend([t] * (triple_count * 3))
            # Pad or trim to match n cells
            if len(pool) < n:
                # Pad remainder with type 0
                while len(pool) < n:
                    pool.append(0)
            elif len(pool) > n:
                pool = pool[:n]
            return pool

        total_groups = n // 3       # e.g. 126 // 3 = 42
        remainder = n % 3           # e.g. 126 % 3 = 0

        # Distribute groups evenly across color types
        base_groups = total_groups // cc        # e.g. 42 // 4 = 10
        extra_groups = total_groups % cc        # e.g. 42 % 4 = 2

        pool = []
        for t in range(cc):
            count = base_groups
            if t < extra_groups:
                count += 1          # first `extra` types get +1 group
            pool.extend([t] * (count * 3))

        # Handle remainder (n not divisible by 3)
        # Pad with different types to spread the imbalance
        for i in range(remainder):
            pool.append(i % cc)

        return pool

    # ── Fix #3: Knob flags computed once, checked during binding ──

    def _compute_knob_flags(self, board: Board, cc: int) -> dict:
        """
        LevelCreateDescribe_OnNewLevel (0x1599004).
        Compute all 5 knob flags ONCE, store for use during binding.
        """
        flags = {
            "less_type": self.less_type,
            "up_easy": self.up_easy,
            "top2_easy": self.top2_easy,
            "top3_easy": self.top3_easy,
            "top4_easy": self.top4_easy,
            "distance": self.distance if self.level_number > 100 else 0,
            "val_replace": self.val_replace and self.level_number >= 51,
        }

        # Pre-compute edge cells (for Knob 1)
        edge_cells = set()
        if self.less_type:
            for layer in board.layers:
                if layer.cells:
                    ys = [c.y for c in layer.cells]
                    mn, mx = min(ys), max(ys)
                    for c in layer.cells:
                        if c.y == mn or c.y == mx:
                            edge_cells.add(id(c))
        flags["edge_cell_ids"] = edge_cells

        # Pre-compute top layer IDs (for Knob 2, 4, top3, top4)
        # Each set is cumulative: top_ids ⊂ top2_ids ⊂ top3_ids ⊂ top4_ids
        top_ids = set()
        top2_ids = set()
        top3_ids = set()
        top4_ids = set()
        if board.layers:
            n = len(board.layers)
            # Top 1 layer
            for c in board.layers[-1].cells:
                top_ids.add(id(c))
            # Top 2 layers
            top2_ids = set(top_ids)
            if n >= 2:
                for c in board.layers[-2].cells:
                    top2_ids.add(id(c))
            # Top 3 layers
            top3_ids = set(top2_ids)
            if n >= 3:
                for c in board.layers[-3].cells:
                    top3_ids.add(id(c))
            # Top 4 layers
            top4_ids = set(top3_ids)
            if n >= 4:
                for c in board.layers[-4].cells:
                    top4_ids.add(id(c))
        flags["top_cell_ids"] = top_ids
        flags["top2_cell_ids"] = top2_ids
        flags["top3_cell_ids"] = top3_ids
        flags["top4_cell_ids"] = top4_ids

        # Effective easy color count
        flags["edge_cc"] = max(2, cc - 2)
        flags["easy_cc"] = max(2, cc - 1)

        return flags

    # ── Fix #1 & #2: Two-pointer with correct ContainsValue + advance ──

    def _bind_random(self, cells, pool, cc, flags, _skip=0):
        """
        GenerateTileIconMapNormal (0x15058D8) — v3 FIXED.

        Key RE insight: The game's ContainsValue check is for the TYPE→ICON
        mapping (ensuring 1-to-1), NOT for cell assignment. Since our simulator
        assigns tile_ids directly to cells (not building a mapping table),
        we do direct pool→cell assignment with shuffled pool.

        Game flow:
          1. Copy icons from tileSetData → pool (field_64)
          2. Shuffle pool (Fisher-Yates, sub_18EB2C8)
          3. Assign pool values to cells in order
          4. Skip pre-assigned cells (HardBgTile = specialSet)
          5. Apply knob flags per-cell during assignment
        """
        random.shuffle(pool)  # Fisher-Yates

        # Knob 3: Distance constraint applied to pool ordering
        dist = flags.get("distance", 0)
        if dist > 0:
            pool = self._apply_distance_constraint(pool, dist)

        # Direct assignment: pool[i] → cell[i], skipping pre-assigned
        pool_idx = 0
        for cell in cells:
            if cell.tile_id >= 0:
                # Pre-assigned (HardBgTile) → skip cell, DON'T consume pool
                continue
            if pool_idx >= len(pool):
                break

            icon_id = pool[pool_idx]
            cell.tile_id = self._apply_knobs_to_cell(cell, icon_id, cc, flags)
            pool_idx += 1

        # Fallback: fill any remaining unassigned
        for c in cells:
            if c.tile_id < 0:
                c.tile_id = random.randint(0, cc - 1)

    # ── Fix #3: Knobs applied per-cell during binding ──

    def _apply_knobs_to_cell(self, cell, icon_id, _cc, flags):
        """
        Apply difficulty knob modifications per-cell (matching game architecture).
        Knobs are FLAGS set before binding, checked during assignment.
        """
        result = icon_id
        cid = id(cell)

        # Knob 1: LessTypeUpDownSide — edge cells restricted to fewer types
        if flags["less_type"] and cid in flags["edge_cell_ids"]:
            result = result % flags["edge_cc"]

        # Knob 2: UpLayerEasy — top layer fewer types
        if flags["up_easy"] and cid in flags["top_cell_ids"]:
            result = result % flags["easy_cc"]

        # Knob 4: TopTwoLayerEasy — top 2 layers fewer types
        if flags["top2_easy"] and cid in flags["top2_cell_ids"]:
            result = result % flags["easy_cc"]

        # Extended Knob: TopThreeLayerEasy — top 3 layers fewer types
        if flags.get("top3_easy") and cid in flags.get("top3_cell_ids", set()):
            result = result % flags["easy_cc"]

        # Extended Knob: TopFourLayerEasy — top 4 layers fewer types
        if flags.get("top4_easy") and cid in flags.get("top4_cell_ids", set()):
            result = result % flags["easy_cc"]

        return result

    def _bind_preset(self, cells, cc, flags, _skip=0):
        """
        DoTileBindingSet (0x1505B38).
        Game reads up to 8 icon groups from tile set config (v40[3..10]),
        then fills cells with icons from each group in round-robin order.

        Each group maps to a tile type. Groups are iterated, and for each
        group, one icon is taken and assigned to the next available slot.
        """
        num_groups = min(8, cc)

        # Simulate 8 icon groups from config
        groups = []
        for g in range(num_groups):
            groups.append(g % cc)

        # Round-robin assignment across groups
        group_idx = 0
        for cell in cells:
            if cell.tile_id >= 0:
                continue  # skip pre-assigned
            icon_id = groups[group_idx % num_groups]
            cell.tile_id = self._apply_knobs_to_cell(cell, icon_id, cc, flags)
            group_idx += 1

    def _assign_hard_bg(self, cells):
        """HardBgTiles pre-assignment (before main binding)."""
        count = min(self.hard_bg_count, len(cells))
        step = max(1, len(cells) // (count + 1))
        assigned = 0
        for i in range(count):
            idx = (i + 1) * step
            if idx < len(cells):
                # HardBg tiles use a dedicated type (high ID to distinguish)
                cells[idx].tile_id = min(8, self._get_effective_cc() - 1)
                assigned += 1
        return assigned

    def _fix_x3_distribution(self, cells, cc):
        """
        Post-process: fix x3 violations caused by knob remapping.

        When _apply_knobs_to_cell uses % easy_cc, it remaps types (e.g. 8→0),
        breaking the x3 pool distribution. This fixes by swapping tiles:

        Strategy per iteration:
          rem=1 + rem=2 → move 1 tile → both become rem=0 (best)
          rem=2 + rem=2 → move 1 tile → rem=1 + rem=0 (progress)
          rem=1 + rem=1 → move 1 tile → rem=0 + rem=2 (creates pair for next iter)

        Converges because each step reduces or maintains total violations.
        """
        for _ in range(len(cells)):
            counts = {}
            for c in cells:
                counts[c.tile_id] = counts.get(c.tile_id, 0) + 1

            r1 = [t for t in counts if counts[t] % 3 == 1]  # types with remainder 1
            r2 = [t for t in counts if counts[t] % 3 == 2]  # types with remainder 2

            if not r1 and not r2:
                break  # all x3

            # Pick best swap pair
            if r1 and r2:
                src, dst = r1[0], r2[0]  # rem1→rem2: both become 0
            elif len(r2) >= 2:
                src, dst = r2[0], r2[1]  # rem2+rem2 → rem1+rem0
            elif len(r1) >= 2:
                src, dst = r1[0], r1[1]  # rem1+rem1 → rem0+rem2
            else:
                break  # single remainder, can't fix (n%3 != 0)

            # Move 1 tile from src type to dst type
            for c in cells:
                if c.tile_id == src:
                    c.tile_id = dst
                    break

    def _apply_distance_constraint(self, pool, min_dist):
        """
        TileDistanceCode — rearrange pool to enforce minimum spacing.
        Applied as a pool reordering step before assignment.
        """
        result = pool.copy()
        n = len(result)
        d = min(min_dist, n // 2)

        for _ in range(n * 2):
            swapped = False
            for i in range(1, n):
                for j in range(max(0, i - d), i):
                    if result[i] == result[j]:
                        cands = [k for k in range(n) if abs(k-i) > d and result[k] != result[i]]
                        if cands:
                            k = random.choice(cands)
                            result[i], result[k] = result[k], result[i]
                            swapped = True
                        break
            if not swapped:
                break
        return result

    def _apply_value_replace(self, cells, cc):
        """
        SetTileValueReplaceData (0x1599174).
        hash = level % 10, check against config lookup table.
        """
        h = self.level_number % 10
        # Lookup table from config.bytes field_496 (HashSet<int>)
        replace_table = {1, 3, 4, 6, 8}

        if h not in replace_table:
            return

        a, b = h % cc, (h + 1) % cc
        if a == b:
            return

        should = False
        if self.val_mode in (1, 3): should = True
        elif self.val_mode == 2: should = True

        if should:
            for c in cells:
                if c.tile_id == a: c.tile_id = b
                elif c.tile_id == b: c.tile_id = a

    def _check_solution(self, board):
        """
        ThereSolutionDescribe (0x159A9A0).
        Phase 1: SetFirstViewLayerThereSolution — top layer ≥1 triplet.
        Phase 2: Check global distribution (all types in multiples of 3).
        """
        if not board.layers:
            return False

        # Check 1: top layer has matching triplet
        top = board.layers[-1]
        counts = {}
        for c in top.cells:
            if c.tile_id >= 0:
                counts[c.tile_id] = counts.get(c.tile_id, 0) + 1
        if not any(v >= 3 for v in counts.values()):
            return False

        # Check 2: global distribution — types should be in multiples of 3
        global_counts = {}
        for c in board.all_cells():
            if c.tile_id >= 0:
                global_counts[c.tile_id] = global_counts.get(c.tile_id, 0) + 1
        # Allow some tolerance (game also has tolerance)
        bad = sum(1 for v in global_counts.values() if v % 3 != 0)
        return bad <= len(global_counts) // 3  # allow up to 1/3 non-x3 types


# ─────────────────────────────────────────────────────────────
# Solver Engine — find solutions, measure complexity
# ─────────────────────────────────────────────────────────────

class TileSolver:
    """
    Simulates Tile Explorer gameplay to find solutions.

    Game mechanics (from RE):
    - Player picks 1 tile from the TOP of any stack (only if not covered)
    - Tile goes to a 7-slot tray at bottom
    - When 3 matching tiles are in the tray → auto-clear
    - If tray is full (7) and no match → GAME OVER (deadlock)
    - Win = all tiles cleared

    This solver uses BFS/DFS to explore possible move sequences.
    """

    TRAY_SIZE = 7  # game's slot tray holds 7 tiles

    @staticmethod
    def analyze(board: Board, max_solutions=100, max_steps=50000) -> dict:
        """
        Full analysis: find solutions, deadlock rate, per-layer steps.

        Returns dict with:
        - solutions_found: number of valid solutions
        - deadlock_rate: % of paths that hit deadlock
        - steps_per_layer: avg steps to clear each layer
        - min_moves: minimum moves to solve
        - complexity_score: 0-100 difficulty rating
        """
        # Build visibility map: which cells are covered by cells above
        vis_map = TileSolver._build_visibility(board)

        # Initial state: all cells active, tray empty
        cell_list = board.all_cells()
        if not cell_list:
            return {"error": "empty board"}

        initial_state = TileSolver._make_state(cell_list, vis_map)

        # BFS/limited DFS to find solutions
        results = TileSolver._search(
            initial_state, cell_list, vis_map, board,
            max_solutions=max_solutions, max_steps=max_steps
        )

        return results

    @staticmethod
    def _build_visibility(board: Board) -> dict:
        """
        Determine which cells block which.

        A cell on layer N+1 at position (x,y) blocks cells on layer N
        at positions within ±0.5 of (x,y) — because tile size is ~1.0
        and half-grid offset means each upper tile covers ~4 lower tiles.
        """
        blocks = {}  # cell_id → set of cell_ids it blocks
        blocked_by = {}  # cell_id → set of cell_ids blocking it

        for c in board.all_cells():
            blocks[id(c)] = set()
            blocked_by[id(c)] = set()

        # For each pair of layers (upper blocks lower)
        for i in range(len(board.layers)):
            for j in range(i + 1, len(board.layers)):
                lower = board.layers[i]
                upper = board.layers[j]
                for uc in upper.cells:
                    for lc in lower.cells:
                        # Tile is 1x1 unit centered at (x,y). Overlap if distance < 1.0.
                        # Verified from IsCanPickUp (0x150D6A8): checks 3 cover-tile refs.
                        if abs(uc.x - lc.x) < 1.0 and abs(uc.y - lc.y) < 1.0:
                            blocks[id(uc)].add(id(lc))
                            blocked_by[id(lc)].add(id(uc))

        return {"blocks": blocks, "blocked_by": blocked_by}

    @staticmethod
    def _make_state(cells, vis_map):
        """Create initial game state."""
        return {
            "active": {id(c) for c in cells},  # cells still on board
            "tray": [],                          # tiles in tray (max 7)
            "moves": 0,
            "cleared": 0,
            "layer_clears": {},                  # layer_idx → move_number when last cell cleared
        }

    @staticmethod
    def _get_pickable(state, cells, vis_map):
        """Get cells that can be picked (visible = not blocked by any active cell)."""
        active = state["active"]
        blocked_by = vis_map["blocked_by"]
        pickable = []
        for c in cells:
            cid = id(c)
            if cid not in active:
                continue
            # Can pick if no active cell blocks it
            blockers = blocked_by.get(cid, set())
            if not blockers.intersection(active):
                pickable.append(c)
        return pickable

    @staticmethod
    def _search(initial, cells, vis_map, board, max_solutions, max_steps):
        """
        Search for solutions using randomized simulation.

        Strategy: run many random playouts, collect statistics.
        """
        solutions = []
        deadlocks = 0
        total_runs = 0
        move_counts = []
        layer_clear_steps = {}  # layer_idx → list of move numbers

        num_cells = len(cells)
        target_runs = max_steps  # number of random playouts (cap removed — caller controls)

        for run in range(target_runs):
            total_runs += 1
            state = {
                "active": {id(c) for c in cells},
                "tray": [],
                "moves": 0,
                "cleared": 0,
            }
            layer_cleared_at = {}
            solved = False

            for step in range(num_cells * 2):  # max steps per run
                pickable = TileSolver._get_pickable(state, cells, vis_map)
                if not pickable:
                    if state["active"]:
                        deadlocks += 1  # stuck with tiles remaining
                    else:
                        solved = True  # all cleared!
                    break

                # Smart pick: prefer tiles that match what's in tray
                # (simulates player strategy — look for matches first)
                tray_types = set(state["tray"])
                matchers = [c for c in pickable if c.tile_id in tray_types]
                # Among matchers, prefer types closest to completing a triplet
                if matchers:
                    tray_counts = {}
                    for t in state["tray"]:
                        tray_counts[t] = tray_counts.get(t, 0) + 1
                    matchers.sort(key=lambda c: -tray_counts.get(c.tile_id, 0))
                    # 70% pick best match, 30% random (human imperfection)
                    if random.random() < 0.7:
                        chosen = matchers[0]
                    else:
                        chosen = random.choice(pickable)
                else:
                    chosen = random.choice(pickable)
                state["active"].discard(id(chosen))
                state["moves"] += 1

                # Tray insertion with TYPE GROUPING (matching game behavior):
                # Same-type tiles sit adjacent in tray. Insert next to matching type.
                tid = chosen.tile_id
                tray = state["tray"]
                inserted = False
                for i in range(len(tray)):
                    if tray[i] == tid:
                        tray.insert(i + 1, tid)
                        inserted = True
                        break
                if not inserted:
                    tray.append(tid)

                # Clear ALL matched triplets (not just one)
                # Game auto-clears every complete triplet after each pick
                changed = True
                while changed:
                    changed = False
                    counts = {}
                    for t in tray:
                        counts[t] = counts.get(t, 0) + 1
                    for t, cnt in counts.items():
                        if cnt >= 3:
                            new_tray = []
                            removed = 0
                            for tv in tray:
                                if tv == t and removed < 3:
                                    removed += 1
                                    state["cleared"] += 1
                                else:
                                    new_tray.append(tv)
                            tray = new_tray
                            state["tray"] = tray
                            changed = True
                            break  # recount after clearing

                # Track layer clears
                layer_idx = chosen.layer_idx
                # Check if this layer is now fully cleared
                layer_active = sum(1 for c in board.layers[layer_idx].cells
                                   if id(c) in state["active"])
                if layer_active == 0 and layer_idx not in layer_cleared_at:
                    layer_cleared_at[layer_idx] = state["moves"]

                # Check deadlock: tray full with no match
                if len(state["tray"]) >= TileSolver.TRAY_SIZE:
                    tray_counts = {}
                    for t in state["tray"]:
                        tray_counts[t] = tray_counts.get(t, 0) + 1
                    if not any(v >= 3 for v in tray_counts.values()):
                        deadlocks += 1
                        break

                # Check win
                if not state["active"]:
                    solved = True
                    break

            if solved:
                solutions.append(state["moves"])
                move_counts.append(state["moves"])
                for li, mv in layer_cleared_at.items():
                    layer_clear_steps.setdefault(li, []).append(mv)

        # Compile results
        total_layers = len(board.layers)
        avg_layer_steps = {}
        for li in range(total_layers):
            steps = layer_clear_steps.get(li, [])
            avg_layer_steps[li] = {
                "avg_moves": round(sum(steps) / len(steps), 1) if steps else -1,
                "clear_rate": round(len(steps) / max(1, len(solutions)) * 100, 1),
                "cells": len(board.layers[li].cells),
            }

        # Complexity score (0-100)
        if total_runs > 0:
            solve_rate = len(solutions) / total_runs
            deadlock_rate = deadlocks / total_runs
        else:
            solve_rate = 0
            deadlock_rate = 1

        complexity = TileSolver._calc_complexity(
            board, solve_rate, deadlock_rate,
            min(move_counts) if move_counts else 999
        )

        # New scoring system
        try:
            new_score = DifficultyScorer.compute_full_score(board, vis_map)
        except Exception:
            new_score = {}

        result = {
            "total_simulations": total_runs,
            "solutions_found": len(solutions),
            "solve_rate": round(solve_rate * 100, 1),
            "deadlock_rate": round(deadlock_rate * 100, 1),
            "min_moves": min(move_counts) if move_counts else None,
            "avg_moves": round(sum(move_counts) / len(move_counts), 1) if move_counts else None,
            "max_moves": max(move_counts) if move_counts else None,
            "layer_analysis": avg_layer_steps,
            "complexity_score": complexity,
            "complexity_label": TileSolver._complexity_label(complexity),
        }
        result.update({"new_" + k: v for k, v in new_score.items()})
        return result

    # @staticmethod
    # def _calc_complexity(board, solve_rate, deadlock_rate, min_moves):
    #     """
    #     [OLD v1] Calculate complexity score 0-100 based on multiple factors.
    #     DEPRECATED — being replaced by new Layout+TilePlacement+Cover system.
    #
    #     Factors (from Tile Explorer's difficulty system):
    #     - Number of layers (more = harder, tiles hidden)
    #     - Cells per layer ratio
    #     - Solve rate from simulation (lower = harder)
    #     - Deadlock rate (higher = harder)
    #     - Minimum moves to solve
    #     """
    #     score = 0
    #
    #     # Factor 1: Layer count (max 30 pts)
    #     nl = len(board.layers)
    #     score += min(30, nl * 3.5)
    #
    #     # Factor 2: Total cells (max 15 pts)
    #     nc = board.total_cells()
    #     score += min(15, nc / 10)
    #
    #     # Factor 3: Deadlock rate (max 30 pts)
    #     score += deadlock_rate * 0.3
    #
    #     # Factor 4: Solve difficulty (max 25 pts)
    #     score += (1 - solve_rate) * 25
    #
    #     return min(100, max(0, round(score)))

    # @staticmethod
    # def _complexity_label(score):
    #     if score < 20: return "Very Easy"
    #     if score < 35: return "Easy"
    #     if score < 50: return "Medium"
    #     if score < 65: return "Hard"
    #     if score < 80: return "Very Hard"
    #     return "Extreme"

    # ── NEW scoring system placeholder (under design) ──
    # See discussion: Layout difficulty + Tile placement difficulty + 100% cover count
    # Formula: Score = Layout×X + InterGroup×Y + IntraGroup×Z + Cover100×K

    @staticmethod
    def _calc_complexity(board, solve_rate, deadlock_rate, min_moves):
        """Temporary stub — returns old-style score until new system is implemented."""
        score = 0
        nl = len(board.layers)
        score += min(30, nl * 3.5)
        nc = board.total_cells()
        score += min(15, nc / 10)
        score += deadlock_rate * 0.3
        score += (1 - solve_rate) * 25
        return min(100, max(0, round(score)))

    @staticmethod
    def _complexity_label(score):
        if score < 20: return "Very Easy"
        if score < 35: return "Easy"
        if score < 50: return "Medium"
        if score < 65: return "Hard"
        if score < 80: return "Very Hard"
        return "Extreme"


# ─────────────────────────────────────────────────────────────
# Difficulty Scorer — new scoring system (Layout + Placement + Cover)
# ─────────────────────────────────────────────────────────────

class DifficultyScorer:
    """
    Difficulty scoring system for level design analysis.
    Aligned with Unity LayoutDifficultyAnalyzer.cs.

    Score = Layout×X + InterGroup×Y + IntraGroup×Z + Cover100×K

    Key concepts (matching Unity source):
    - resolveScore: BFS count of ALL unique covering tiles above (not just chain depth)
    - coverage: 4-corner overlap check (0-4), not binary
    - effectiveScore: resolveScore on filtered board, minus 1 if same-type within 2 layers
    - strip: remove tiles with coverage==0, pick 3 prioritizing highest layer
    """

    OVERLAP_TOL = 0.05  # LayoutDesignConstants.REMOVE_TOLERANCE

    # ── Coverage: 4-corner overlap (matching Unity CalculateCoverage) ──

    @staticmethod
    def _tile_rect(x, y):
        """Get tile bounding rect matching Unity: Rect(x-0.5-tol, y-0.5-tol, 1-tol*2, 1-tol*2)."""
        tol = DifficultyScorer.OVERLAP_TOL
        x_min = x - 0.5 - tol
        y_min = y - 0.5 - tol
        w = 1.0 - tol * 2
        return (x_min, y_min, x_min + w, y_min + w)

    @staticmethod
    def _rect_contains(rect, px, py):
        """Match Unity Rect.Contains: min <= p < max (strict upper bound)."""
        return rect[0] <= px < rect[2] and rect[1] <= py < rect[3]

    @staticmethod
    def _rects_overlap(r1, r2):
        return not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1])

    @staticmethod
    def compute_coverage(target_cell, covering_cells):
        """
        4-corner coverage check (matching Unity).
        Returns 0-4: how many corners of target are covered by any covering cell.
        """
        tx, ty = target_cell.x, target_cell.y

        # Quick check: exact same position = 4 (full cover)
        for c in covering_cells:
            if abs(tx - c.x) < 0.01 and abs(ty - c.y) < 0.01:
                return 4

        # Filter covers within distance 2.0
        near_covers = []
        for c in covering_cells:
            dist = ((tx - c.x)**2 + (ty - c.y)**2)**0.5
            if dist <= 2.0:
                near_covers.append(DifficultyScorer._tile_rect(c.x, c.y))

        if not near_covers:
            return 0

        # Check 4 corners of target rect
        t_rect = DifficultyScorer._tile_rect(tx, ty)
        corners = [
            (t_rect[0], t_rect[1]),  # bottom-left
            (t_rect[0], t_rect[3]),  # top-left
            (t_rect[2], t_rect[1]),  # bottom-right
            (t_rect[2], t_rect[3]),  # top-right
        ]

        overlap_count = 0
        for px, py in corners:
            for cr in near_covers:
                if DifficultyScorer._rect_contains(cr, px, py):
                    overlap_count += 1
                    break

        return overlap_count

    # ── Resolve Score: BFS unique covering tile count (matching Unity) ──

    @staticmethod
    def compute_resolve_scores(board, vis_map=None) -> dict:
        """
        BFS count of ALL unique tiles above each cell.
        Matching Unity CountUniqueCoveringTiles: Rect.Overlaps per layer.
        """
        all_cells = board.all_cells()

        # Build layer map (matching Unity BuildLayerMap)
        layer_map = {}
        for c in all_cells:
            layer_map.setdefault(c.layer_idx, []).append(c)
        max_layer = max(layer_map.keys()) if layer_map else 0

        def _rect(c):
            return DifficultyScorer._tile_rect(c.x, c.y)

        def _overlaps(r1, r2):
            return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])

        scores = {}
        for c in all_cells:
            visited = {id(c)}
            queue = [c]
            count = 0
            while queue:
                current = queue.pop(0)
                cr = _rect(current)
                for check_layer in range(current.layer_idx + 1, max_layer + 1):
                    for cover in layer_map.get(check_layer, []):
                        if id(cover) in visited:
                            continue
                        if _overlaps(cr, _rect(cover)):
                            visited.add(id(cover))
                            queue.append(cover)
                            count += 1
            scores[id(c)] = count

        return scores

    @staticmethod
    def layout_score(resolve_scores) -> float:
        """Average resolve score across all tiles (matching Unity)."""
        if not resolve_scores:
            return 0.0
        return sum(resolve_scores.values()) / len(resolve_scores)

    # ── Effective Score: BFS + same-type reduction (matching Unity v2) ──

    @staticmethod
    def _compute_effective_on_active(board, active, eff_layers=None):
        """
        Compute effective scores on active tiles.
        Step 1: BFS CountUniqueCoveringTiles with Rect.Overlaps (uses physical layers)
        Step 2: Subtract 1 if same-type at HIGHER effective_layer overlaps.
                If eff_layers None, falls back to physical layer comparison.
        """
        cell_map = {id(c): c for c in board.all_cells()}

        # Build layer map for active cells
        layer_map = {}
        for cid in active:
            c = cell_map.get(cid)
            if c:
                layer_map.setdefault(c.layer_idx, []).append(c)
        max_layer = max(layer_map.keys()) if layer_map else 0

        def _rect(c):
            return DifficultyScorer._tile_rect(c.x, c.y)

        def _overlaps(r1, r2):
            return not (r1[2] <= r2[0] or r2[2] <= r1[0] or r1[3] <= r2[1] or r2[3] <= r1[1])

        # Step 1: BFS using Rect.Overlaps per physical layer
        scores = {}
        for cid in active:
            c = cell_map.get(cid)
            if not c:
                continue
            visited = {id(c)}
            queue = [c]
            count = 0
            while queue:
                current = queue.pop(0)
                cr = _rect(current)
                for check_layer in range(current.layer_idx + 1, max_layer + 1):
                    for cover in layer_map.get(check_layer, []):
                        if id(cover) in visited:
                            continue
                        if _overlaps(cr, _rect(cover)):
                            visited.add(id(cover))
                            queue.append(cover)
                            count += 1
            scores[cid] = count

        # Step 2: Same-type reduction — subtract 1 if any same-type at PHYSICAL layer above overlaps.
        # Design choice: keep -1 (NOT -N count) — tiles fully hidden under same-type stack
        # aren't truly "easy" from player perspective (player can't see them).
        # Iteration over physical layers above (c.layer_idx + 1) already enforces "above me".
        for cid in active:
            c = cell_map.get(cid)
            if not c or c.tile_id < 0:
                continue
            cr = _rect(c)
            found = False
            for check_layer in range(c.layer_idx + 1, max_layer + 1):
                for other in layer_map.get(check_layer, []):
                    if other.tile_id == c.tile_id and _overlaps(cr, _rect(other)):
                        found = True
                        break
                if found:
                    break
            if found:
                scores[cid] = scores.get(cid, 0) - 1

        return scores

    @staticmethod
    def compute_effective_scores(board, vis_map, active) -> dict:
        """
        Public API for effective scores (calls _compute_effective_on_active).
        Kept for backward compatibility.
        """
        return DifficultyScorer._compute_effective_on_active(board, active)

    # ── Coverage computation for active set ──

    @staticmethod
    def _compute_coverages(board, active):
        """Compute 4-corner coverage for each active cell."""
        cell_map = {id(c): c for c in board.all_cells()}
        coverages = {}

        # Build layer map for active cells
        active_cells = [cell_map[cid] for cid in active if cid in cell_map]

        for cid in active:
            c = cell_map.get(cid)
            if not c:
                continue
            # Covering cells = active cells on higher layers
            covers = [oc for oc in active_cells
                      if oc.layer_idx > c.layer_idx and id(oc) != cid]
            coverages[cid] = DifficultyScorer.compute_coverage(c, covers)

        return coverages

    @staticmethod
    def _rect_area(r):
        """Area of a rect (x_min, y_min, x_max, y_max)."""
        w = max(0.0, r[2] - r[0])
        h = max(0.0, r[3] - r[1])
        return w * h

    @staticmethod
    def _rect_intersect(r1, r2):
        """Intersection rect of r1 and r2, or None if no overlap."""
        x_min = max(r1[0], r2[0])
        y_min = max(r1[1], r2[1])
        x_max = min(r1[2], r2[2])
        y_max = min(r1[3], r2[3])
        if x_max <= x_min or y_max <= y_min:
            return None
        return (x_min, y_min, x_max, y_max)

    @staticmethod
    def _union_area(rects):
        """Area of union of axis-aligned rects via sweep-line on x-coordinates."""
        if not rects:
            return 0.0
        # Collect distinct x coordinates
        xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
        total = 0.0
        for i in range(len(xs) - 1):
            x_lo, x_hi = xs[i], xs[i + 1]
            if x_hi <= x_lo:
                continue
            # For this x-strip, union of y-intervals
            intervals = []
            for r in rects:
                if r[0] <= x_lo and r[2] >= x_hi:
                    intervals.append((r[1], r[3]))
            if not intervals:
                continue
            intervals.sort()
            merged_y = 0.0
            cur_lo, cur_hi = intervals[0]
            for lo, hi in intervals[1:]:
                if lo <= cur_hi:
                    cur_hi = max(cur_hi, hi)
                else:
                    merged_y += cur_hi - cur_lo
                    cur_lo, cur_hi = lo, hi
            merged_y += cur_hi - cur_lo
            total += (x_hi - x_lo) * merged_y
        return total

    # Visual tile size — full 1×1 grid (matches game rendering, no visible gap).
    # 4 corner tiles fully cover center tile (cover100 ✓).
    VISUAL_TILE_SIZE = 1.0

    @staticmethod
    def _tile_rect_full(x, y):
        """Symmetric 1×1 tile rect (matching game visual rendering, centered at x,y).
        Used for area-based cover100. 4-corner overlap = 100% coverage."""
        h = DifficultyScorer.VISUAL_TILE_SIZE / 2
        return (x - h, y - h, x + h, y + h)

    @staticmethod
    def pickable_diversity(board, active):
        """Count distinct tile types among pickable cells (cells with no active blockers above).
        High value = many distinct types visible = loose start (harder for player).
        Low value = few types visible = concentrated triples available (easier)."""
        cell_map = {id(c): c for c in board.all_cells()}
        active_cells = [cell_map[cid] for cid in active if cid in cell_map]

        # Find pickable cells in active set
        pickable_types = set()
        for cid in active:
            c = cell_map.get(cid)
            if not c or c.tile_id < 0:
                continue
            # Pickable = no active cell at higher physical layer overlapping
            blocked = False
            for oc in active_cells:
                if id(oc) == cid: continue
                if oc.layer_idx > c.layer_idx and abs(oc.x - c.x) < 1.0 and abs(oc.y - c.y) < 1.0:
                    blocked = True
                    break
            if not blocked:
                pickable_types.add(c.tile_id)
        return len(pickable_types)

    @staticmethod
    def cover100_by_area(board, active, threshold=0.9):
        """Count cells where ≥ threshold (default 90%) of tile surface area is covered
        by other active cells at HIGHER physical layers (top-down vertical view).
        Uses full 1×1 tile rect (matching game rendering, not Unity overlap-tol rect)."""
        cell_map = {id(c): c for c in board.all_cells()}
        active_cells = [cell_map[cid] for cid in active if cid in cell_map]

        count = 0
        for cid in active:
            c = cell_map.get(cid)
            if not c:
                continue
            t_rect = DifficultyScorer._tile_rect_full(c.x, c.y)
            t_area = DifficultyScorer._rect_area(t_rect)
            if t_area <= 0:
                continue
            # Collect intersection rects from higher-layer covers
            intersect_rects = []
            for oc in active_cells:
                if id(oc) == cid: continue
                if oc.layer_idx <= c.layer_idx: continue
                o_rect = DifficultyScorer._tile_rect_full(oc.x, oc.y)
                inter = DifficultyScorer._rect_intersect(t_rect, o_rect)
                if inter is not None:
                    intersect_rects.append(inter)
            if not intersect_rects:
                continue
            covered_area = DifficultyScorer._union_area(intersect_rects)
            if covered_area / t_area >= threshold:
                count += 1
        return count

    @staticmethod
    def compute_effective_layers(board, active):
        """Compute effective_layer for each active cell.

        effective_layer = (number of distinct higher physical layers that have
        at least one overlapping cell on this position) + 1.

        - Tile at top with nothing above: effective_layer = 1
        - Tile buried under N distinct higher layers: effective_layer = N + 1

        Used by:
        - Strip 2-layer window (uses effective_layer instead of physical layer_idx)
        - cover100 (cells with effective_layer == max(effective_layer values))
        - Effective scores same-type subtract (uses effective_layer comparisons)

        layout score still uses physical layer_idx (full board BFS).
        """
        cell_map = {id(c): c for c in board.all_cells()}
        active_cells = [cell_map[cid] for cid in active if cid in cell_map]

        eff = {}
        for cid in active:
            c = cell_map.get(cid)
            if not c:
                continue
            higher_layers_with_overlap = set()
            for oc in active_cells:
                if id(oc) == cid:
                    continue
                if oc.layer_idx > c.layer_idx and abs(oc.x - c.x) < 1.0 and abs(oc.y - c.y) < 1.0:
                    higher_layers_with_overlap.add(oc.layer_idx)
            eff[cid] = len(higher_layers_with_overlap) + 1
        return eff

    # ── Strip: pick 3 tiles within 2-layer window (matching Unity v2) ──

    @staticmethod
    def _pick_three_tiles(candidates, randomize=False):
        """
        Pick exactly 3 tiles from candidates, prioritizing highest layer first.
        randomize=False: deterministic (sort by position hash)
        randomize=True/DotNetRandom: random tie-break within same layer
        """
        sorted_cands = sorted(candidates, key=lambda c: -c.layer_idx)
        if not randomize:
            sorted_cands = sorted(candidates,
                                  key=lambda c: (-c.layer_idx, int(c.x) * 1000 + int(c.y)))
            return sorted_cands[:3]

        # Random tie-break using DotNetRandom (matching Unity's System.Random shuffle)
        rng = randomize if isinstance(randomize, DotNetRandom) else None
        result = []
        i = 0
        while len(result) < 3 and i < len(sorted_cands):
            current_layer = sorted_cands[i].layer_idx
            same_layer = []
            while i < len(sorted_cands) and sorted_cands[i].layer_idx == current_layer:
                same_layer.append(sorted_cands[i])
                i += 1
            needed = 3 - len(result)
            if len(same_layer) <= needed:
                result.extend(same_layer)
            else:
                # Fisher-Yates shuffle (matching Unity _rng.Next(j+1))
                if rng:
                    for j in range(len(same_layer) - 1, 0, -1):
                        k = rng.next(j + 1)
                        same_layer[j], same_layer[k] = same_layer[k], same_layer[j]
                else:
                    random.shuffle(same_layer)
                result.extend(same_layer[:needed])
        return result

    @staticmethod
    def _find_triple_within_2_layers(candidates, randomize=False, eff_layers=None):
        """
        Find 3 tiles from candidates where all are within a 2-effective-layer range.

        If eff_layers dict provided: use effective_layer (#layers above + 1).
        Otherwise: fall back to physical layer_idx.
        """
        if len(candidates) < 3:
            return None

        # Layer key: effective_layer if provided, else physical layer_idx
        def lk(c):
            return eff_layers[id(c)] if eff_layers is not None and id(c) in eff_layers else c.layer_idx

        # Sort by layer descending (highest first)
        sorted_cands = sorted(candidates, key=lambda c: -lk(c))

        # Sliding window
        for i in range(len(sorted_cands) - 2):
            highest_layer = lk(sorted_cands[i])
            window = []
            for j in range(i, len(sorted_cands)):
                if highest_layer - lk(sorted_cands[j]) <= 2:
                    window.append(sorted_cands[j])
                else:
                    break

            if len(window) >= 3:
                return DifficultyScorer._pick_three_tiles(window, randomize)

        return None

    @staticmethod
    def strip_easy_triples(board, active_set, randomize=False):
        """
        Iteratively strip triples (matching Unity v2 CalculateEffectiveScores loop):

        Each iteration:
        1. Recalculate coverage for remaining tiles
        2. Compute effectiveScore (BFS) on remaining tiles
        3. Subtract 1 if same-type in ANY layer above overlaps
        4. Find tiles with effectiveScore <= 0, group by type
        5. Find triples within 2-layer window, remove them
        6. Repeat until no more triples found

        Returns (active_set, stripped_count).
        """
        cell_map = {id(c): c for c in board.all_cells()}
        active = set(active_set)
        stripped = 0

        for _ in range(len(cell_map)):  # max iterations safety
            # Compute effective_layer (recalculated each iteration as active set shrinks)
            eff_layers = DifficultyScorer.compute_effective_layers(board, active)

            # Steps 1-3: Compute effective scores (uses eff_layers for same-type check)
            eff_scores = DifficultyScorer._compute_effective_on_active(board, active, eff_layers)

            # Step 4: Find tiles with effectiveScore <= 0, group by type
            zero_by_type = {}
            for cid in active:
                if eff_scores.get(cid, 0) > 0:
                    continue
                c = cell_map.get(cid)
                if c and c.tile_id >= 0:
                    zero_by_type.setdefault(c.tile_id, []).append(c)

            # Step 5: Find triples within 2-effective-layer window
            to_remove = set()
            for tid, cells_of_type in zero_by_type.items():
                triple = DifficultyScorer._find_triple_within_2_layers(
                    cells_of_type, randomize, eff_layers)
                if triple is not None:
                    for c in triple:
                        to_remove.add(id(c))

            if not to_remove:
                break

            for cid in to_remove:
                active.discard(cid)
            stripped += len(to_remove) // 3

        return active, stripped

    # ── InterGroup / IntraGroup (same formula as before, using effectiveScore) ──

    @staticmethod
    def inter_group_score(effective_scores, cells, active) -> float:
        """Average of (average effective score per tile type), normalized by number of types.
        ALL tiles included — stripped tiles have effectiveScore=0."""
        type_scores = {}
        for c in cells:
            if c.tile_id < 0:
                continue
            cid = id(c)
            # Stripped tiles: effectiveScore = 0 (not in effective_scores dict)
            type_scores.setdefault(c.tile_id, []).append(effective_scores.get(cid, 0))

        total = 0.0
        for tid, vals in type_scores.items():
            if vals:
                total += sum(vals) / len(vals)
        return total

    @staticmethod
    def intra_group_score(effective_scores, cells, active) -> float:
        """Sum of (max - min) / count per tile type.
        ALL tiles included — stripped tiles have effectiveScore=0 (matching Unity)."""
        type_scores = {}
        for c in cells:
            if c.tile_id < 0:
                continue
            type_scores.setdefault(c.tile_id, []).append(effective_scores.get(id(c), 0))

        total = 0.0
        for tid, vals in type_scores.items():
            if len(vals) > 0:
                total += (max(vals) - min(vals)) / len(vals)
        return total

    # ── Cover 100%: coverage == 4 (matching Unity — on original board) ──

    @staticmethod
    def cover100_count(board, active) -> int:
        """
        Count tiles with coverage == 4 (all 4 corners covered).
        Called on original board (before strip) to match Unity CSV report.
        """
        coverages = DifficultyScorer._compute_coverages(board, active)
        return sum(1 for cid in active if coverages.get(cid, 0) == 4)

    # ── Full Pipeline ──

    @staticmethod
    def compute_full_score(board, vis_map=None, weights=None, randomize_strip=False) -> dict:
        """
        Full scoring pipeline aligned with Unity v2 LayoutDifficultyAnalyzer.

        Pipeline:
        1. Compute resolve scores (BFS unique covering count) for layout score
        2. Iterative strip loop (effectiveScore<=0 + 2-layer window):
           a. Recalculate coverage on remaining tiles
           b. Compute effectiveScore (BFS) on remaining tiles
           c. Subtract 1 if same-type in ANY layer above overlaps
           d. Find tiles with effectiveScore<=0, pick triples within 2 layers
           e. Remove triples, repeat until stable
        3. Compute final effectiveScore on remaining tiles
        4. InterGroup / IntraGroup from effective scores
        5. Cover100 = tiles with coverage==4 after strip
        6. Weighted final score
        """
        if vis_map is None:
            vis_map = TileSolver._build_visibility(board)
        if weights is None:
            weights = load_scoring_weights()

        all_cells = board.all_cells()
        if not all_cells:
            return {"layout": 0, "inter_group": 0, "intra_group": 0,
                    "cover100": 0, "final_score": 0, "stripped": 0}

        # Step 1: Resolve scores & layout (on full board, uses physical layers)
        resolve_scores = DifficultyScorer.compute_resolve_scores(board, vis_map)
        layout = DifficultyScorer.layout_score(resolve_scores)

        # Step 2: Iterative strip (effectiveScore<=0 + 2-effective-layer window)
        all_active = {id(c) for c in all_cells}
        active = set(all_active)
        active, stripped = DifficultyScorer.strip_easy_triples(board, active, randomize_strip)

        # Step 3: Effective layers on remaining tiles (recomputed after strip)
        eff_layers = DifficultyScorer.compute_effective_layers(board, active)

        # Step 4: Final effective scores using eff_layers for same-type subtract
        effective = DifficultyScorer._compute_effective_on_active(board, active, eff_layers)

        # Step 5: InterGroup / IntraGroup
        inter = DifficultyScorer.inter_group_score(effective, all_cells, active)
        intra = DifficultyScorer.intra_group_score(effective, all_cells, active)

        # Step 6: Cover 100% — cells where ≥90% surface area covered by active higher-layer cells
        cover = DifficultyScorer.cover100_by_area(board, active, threshold=0.9)

        # Step 7: Pickable diversity — # distinct types visible at game start
        pick_div = DifficultyScorer.pickable_diversity(board, active)

        # Step 8: Weighted final score
        X = weights.get("X", 1.0)
        Y = weights.get("Y", 1.0)
        Z = weights.get("Z", 1.0)
        K = weights.get("K", 0.5)
        D = weights.get("D", 0.5)  # pickable_diversity weight
        final = layout * X + inter * Y + intra * Z + cover * K + pick_div * D

        return {
            "layout": round(layout, 2),
            "inter_group": round(inter, 2),
            "intra_group": round(intra, 2),
            "cover100": cover,
            "pickable_diversity": pick_div,
            "stripped": stripped,
            "final_score": round(final, 2),
            "remaining_tiles": len(active),
            "weights": {"X": X, "Y": Y, "Z": Z, "K": K, "D": D, "Z_doubled": True},
        }

    @staticmethod
    def batch_score(board, engine, weights=None, n_runs=50) -> dict:
        """
        Run generate N times on same layout, collect min/max/avg of each score component.
        Used for Min/Max report to show difficulty range of a layout.
        """
        if weights is None:
            weights = load_scoring_weights()

        vis_map = TileSolver._build_visibility(board)
        results = []

        for _ in range(n_runs):
            engine.generate(board)
            r = DifficultyScorer.compute_full_score(board, vis_map, weights)
            results.append(r)

        if not results:
            return {}

        keys = ["layout", "inter_group", "intra_group", "cover100", "final_score"]
        summary = {}
        for k in keys:
            vals = [r[k] for r in results]
            summary[k] = {
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "avg": round(sum(vals) / len(vals), 2),
            }
        summary["n_runs"] = n_runs
        summary["stripped_avg"] = round(sum(r["stripped"] for r in results) / len(results), 1)

        return summary


# ─────────────────────────────────────────────────────────────
# Board Loader — supports folder import, file import, multi-format
# ─────────────────────────────────────────────────────────────

DEFAULT_LEVELS_DIR = r"D:\_Rac\tile_explorer\Levels_JSON"
# Mutable: App can change this at runtime
_levels_dir = DEFAULT_LEVELS_DIR


def set_levels_dir(path):
    global _levels_dir
    _levels_dir = path


def get_levels_dir():
    return _levels_dir


def list_level_files(directory=None):
    d = directory or _levels_dir
    if not os.path.isdir(d): return []
    return sorted(f for f in os.listdir(d) if f.endswith(".json")
                  and not f.startswith("_"))  # skip _index.json etc.


def _parse_layers_from_data(layers_data):
    """Parse layers from JSON data — handles all known formats."""
    layers = []
    for ld in layers_data:
        layer = Layer(ld.get("layer", ld.get("id", ld.get("index", len(layers)))))
        # Format 4 (stones): layers[].stones[] with {i, x, y}
        cells_data = ld.get("cells", ld.get("stones", []))
        for ci, cd in enumerate(cells_data):
            if "x" in cd and "y" in cd:
                # Ensure numeric coords (some JSON files store as string)
                c = layer.add(float(cd["x"]), float(cd["y"]))
                # Restore tile_id: "tile", "tile_id", or "i" (stones format)
                if c and "tile" in cd:
                    c.tile_id = int(cd["tile"])
                elif c and "tile_id" in cd:
                    c.tile_id = int(cd["tile_id"])
                elif c and "i" in cd:
                    c.tile_id = int(cd["i"])
            else:
                # Old format (level0, level3): no coords, arrange in grid
                cols = max(1, int(len(cells_data) ** 0.5))
                layer.add(float(ci % cols), float(-(ci // cols)))
        layers.append(layer)
    return layers


def load_board(filename, board_idx=0, directory=None):
    """
    Load board from a JSON file. Auto-detects format:

    Format 1 — Game parsed (from parse_all_levels.py):
      {"boards": [{"board": 0, "layers": [{"layer": 0, "cells": [{"x":..,"y":..}]}]}]}

    Format 2 — Tool export (from Export JSON / metadata):
      {"layers": [{"id": 0, "cells": [{"x":.., "y":.., "tile": 3}]}]}
      or {"metadata": {...}, "layers": [...]}

    Format 3 — Batch export (from Finder):
      {"boards": [{"source": {...}, "layers": [...]}]}
      or {"source": {...}, "layers": [...]}
    """
    d = directory or _levels_dir
    path = os.path.join(d, filename) if not os.path.isabs(filename) else filename
    if not os.path.exists(path): return None

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return None

    name_base = os.path.basename(path).replace(".json", "")

    # Format 1: Game parsed — has "boards" array with "layers" inside each board
    if "boards" in data and isinstance(data["boards"], list):
        boards = data["boards"]
        if board_idx >= len(boards): return None
        bd = boards[board_idx]
        # Check if it's batch export format (has "layers" at board level)
        layers_data = bd.get("layers", [])
        board = Board(f"{name_base} #{board_idx}")
        board.layers = _parse_layers_from_data(layers_data)
        return board

    # Format 4: Stones/stacks format (detect BEFORE Format 2)
    # {"group":1, "tiles":"", "layers":[{"index":0,"stones":[{"i":..,"x":..,"y":..}]}], "stacks":[...]}
    if "layers" in data and isinstance(data["layers"], list):
        first = data["layers"][0] if data["layers"] else {}
        if "stones" in first:
            board = Board(f"{name_base} (g{data.get('group', '?')})")
            board.layers = _parse_layers_from_data(data["layers"])
            # Store stacks/group/tiles for export roundtrip
            if "stacks" in data:
                board._stacks = data["stacks"]
            if "group" in data:
                board._group = data["group"]
            if "tiles" in data:
                board._tiles_str = data["tiles"]
            return board

    # Format 2: Single board export — has "layers" at top level
    if "layers" in data and isinstance(data["layers"], list):
        board = Board(data.get("metadata", {}).get("board_name", name_base))
        board.layers = _parse_layers_from_data(data["layers"])
        return board

    # Format 3: Has "source" + "layers" (single board from batch)
    if "source" in data and "layers" in data:
        src = data["source"]
        board = Board(f"{src.get('file', name_base)} #{src.get('board', 0)}")
        board.layers = _parse_layers_from_data(data["layers"])
        return board

    return None


def export_board_stones_format(board, group=1, tiles_str="") -> dict:
    """
    Export board to stones/stacks format (Format 4).

    Output format:
    {
      "group": 1,
      "tiles": "",
      "layers": [{"index": 0, "stones": [{"i": tile_id, "x": x, "y": y}, ...]}],
      "stacks": [{"x": x, "y": y, "d": 1}, ...]
    }

    - "i" = tile_id (icon index)
    - "stacks" = positions that appear in all layers (stack columns), or
      restored from board._stacks if available (roundtrip preservation)
    """
    layers_out = []
    for li, layer in enumerate(board.layers):
        stones = []
        for c in layer.cells:
            stone = {"i": c.tile_id if c.tile_id >= 0 else 0, "x": c.x, "y": c.y}
            stones.append(stone)
        layers_out.append({"index": li, "stones": stones})

    # Stacks: preserve from import if available, otherwise auto-detect
    stacks = getattr(board, '_stacks', None)
    if stacks is None:
        # Auto-detect: find positions that exist in the bottom layer
        # (stacks are typically the bottom row shared across layers)
        stacks = []
        if board.layers:
            bottom = board.layers[0]
            for c in bottom.cells:
                stacks.append({"x": c.x, "y": c.y, "d": 1})

    # Preserve group/tiles from import if available
    grp = getattr(board, '_group', group)
    tiles = getattr(board, '_tiles_str', tiles_str)

    return {
        "group": grp,
        "tiles": tiles,
        "layers": layers_out,
        "stacks": stacks,
    }


def load_board_from_file(filepath, board_idx=0):
    """Load from absolute path — for Import File."""
    return load_board(filepath, board_idx, directory="")


def get_board_count(filename, directory=None):
    d = directory or _levels_dir
    path = os.path.join(d, filename) if not os.path.isabs(filename) else filename
    if not os.path.exists(path): return 0
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return 0
    if "boards" in data:
        return len(data.get("boards", []))
    if "layers" in data:
        return 1  # single board file
    return 0

def make_sample_board():
    """Fallback sample if Levels_JSON not found."""
    board = Board("Sample Diamond 6L")
    for li in range(6):
        layer = Layer(li)
        r = max(1, 3 - li // 2)
        off = 0.5 if li % 2 else 0.0
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) + abs(dy) <= r:
                    layer.add(dx + off, dy + off)
        board.layers.append(layer)
    return board


# ─────────────────────────────────────────────────────────────
# Canvas
# ─────────────────────────────────────────────────────────────

class SimCanvas(tk.Canvas):
    CS = 36  # cell size base

    def __init__(self, parent, **kw):
        super().__init__(parent, bg="#16161E", highlightthickness=0, **kw)
        self.board = None
        self.zoom = 1.0
        self.ox = self.oy = 0.0
        self._d = None
        self.show = "all"  # "all", "active", "upto"
        self.active_layer = 0
        self.view_3d = False  # 3D isometric mode
        self.bind("<Button-2>", self._ps); self.bind("<B2-Motion>", self._pm)
        self.bind("<Button-3>", self._ps); self.bind("<B3-Motion>", self._pm)
        self.bind("<MouseWheel>", self._scroll)
        self.bind("<Configure>", lambda e: self.paint())

    def w2s(self, x, y, layer_idx=0):
        """World to screen. In 3D mode, applies isometric projection + layer height."""
        cx, cy = self.winfo_width()/2, self.winfo_height()/2
        if self.view_3d:
            # Isometric: x goes right-down, y goes left-down, layer goes up
            iso_x = (x - y) * 0.7
            iso_y = (x + y) * 0.35 - layer_idx * 0.6
            return (cx + iso_x * self.CS * self.zoom + self.ox,
                    cy + iso_y * self.CS * self.zoom + self.oy)
        else:
            return (cx + x * self.CS * self.zoom + self.ox,
                    cy - y * self.CS * self.zoom + self.oy)

    def paint(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10: return
        if not self.view_3d:
            self._grid(w, h)
        if not self.board:
            self.create_text(w/2, h/2, text="Load a board to begin",
                             fill="#444", font=("Segoe UI", 13))
            return
        nl = len(self.board.layers)

        if self.view_3d:
            self._paint_3d(nl)
        else:
            self._paint_2d(nl)

    def _paint_2d(self, nl):
        for i, layer in enumerate(self.board.layers):
            if self.show == "active" and i != self.active_layer: continue
            if self.show == "upto" and i > self.active_layer: continue
            self._draw_layer_2d(layer, i, i == self.active_layer)
        sx, sy = self.w2s(0, 0)
        self.create_oval(sx-3, sy-3, sx+3, sy+3, fill="#444466", outline="")

    def _paint_3d(self, nl):
        """Draw all layers in isometric 3D view — bottom to top with depth."""
        # Sort cells by draw order: back-to-front (higher y first), then layer
        draw_list = []
        for i, layer in enumerate(self.board.layers):
            if self.show == "active" and i != self.active_layer: continue
            if self.show == "upto" and i > self.active_layer: continue
            for cell in layer.cells:
                # Sort key: lower layers first, then by y desc, x asc (back to front)
                draw_list.append((i, cell, i * 1000 + (cell.x + cell.y) * 10))
        draw_list.sort(key=lambda t: t[2])

        for layer_idx, cell, _ in draw_list:
            self._draw_cell_3d(cell, layer_idx, layer_idx == self.active_layer, nl)

    def _draw_cell_3d(self, cell, layer_idx, active, total):
        """Draw a single cell as an isometric tile with height/shadow."""
        sz = self.CS * self.zoom * 0.75
        half = sz / 2
        depth = sz * 0.3  # tile thickness

        sx, sy = self.w2s(cell.x, cell.y, layer_idx)

        if cell.tile_id >= 0 and cell.tile_id < len(TILE_COLORS):
            bc, lb, _ = TILE_COLORS[cell.tile_id]
        else:
            bc = LAYER_COLORS[layer_idx % len(LAYER_COLORS)]
            lb = ""

        if not active:
            bc = self._dim(bc, 0.35)
        dark = self._dim(bc, 0.55)

        # Top face (parallelogram)
        top = [sx - half, sy - half * 0.5,
               sx, sy - half,
               sx + half, sy - half * 0.5,
               sx, sy]
        self.create_polygon(top, fill=bc, outline="#333" if active else "#222", width=1)

        # Right face
        right = [sx + half, sy - half * 0.5,
                 sx, sy,
                 sx, sy + depth,
                 sx + half, sy - half * 0.5 + depth]
        self.create_polygon(right, fill=dark, outline="#222", width=1)

        # Left face
        left = [sx - half, sy - half * 0.5,
                sx, sy,
                sx, sy + depth,
                sx - half, sy - half * 0.5 + depth]
        self.create_polygon(left, fill=self._dim(bc, 0.7), outline="#222", width=1)

        # Label on top face
        if self.zoom > 0.4 and lb:
            self.create_text(sx, sy - half * 0.25, text=lb,
                             fill="#FFF" if active else "#999",
                             font=("Consolas", max(6, int(10 * self.zoom)), "bold"))

    def _grid(self, w, h):
        s = self.CS * self.zoom
        if s < 5: return
        cx, cy = w/2+self.ox, h/2+self.oy
        x0 = cx % s; y0 = cy % s
        for x in range(int(-s), w+int(s), max(1, int(s))):
            self.create_line(x0+x, 0, x0+x, h, fill="#1E1E2A")
        for y in range(int(-s), h+int(s), max(1, int(s))):
            self.create_line(0, y0+y, w, y0+y, fill="#1E1E2A")

    def _draw_layer_2d(self, layer, idx, active):
        sz = self.CS * self.zoom * 0.82
        half = sz / 2
        for cell in layer.cells:
            sx, sy = self.w2s(cell.x, cell.y)
            if cell.tile_id >= 0 and cell.tile_id < len(TILE_COLORS):
                bc, lb, _ = TILE_COLORS[cell.tile_id]
            else:
                bc = LAYER_COLORS[idx % len(LAYER_COLORS)]
                lb = ""
            if active:
                fill, ol, ow = bc, "#FFF", 2
            else:
                fill = self._dim(bc, 0.22)
                ol = self._dim(bc, 0.35)
                ow = 1
            r = max(2, 5 * self.zoom)
            p = [sx-half+r,sy-half, sx+half-r,sy-half,
                 sx+half,sy-half, sx+half,sy-half+r,
                 sx+half,sy+half-r, sx+half,sy+half,
                 sx+half-r,sy+half, sx-half+r,sy+half,
                 sx-half,sy+half, sx-half,sy+half-r,
                 sx-half,sy-half+r, sx-half,sy-half]
            self.create_polygon(p, smooth=True, fill=fill, outline=ol, width=ow)
            if self.zoom > 0.45 and lb:
                self.create_text(sx, sy, text=lb,
                                 fill="#FFF" if active else "#777",
                                 font=("Consolas", max(7, int(11*self.zoom)), "bold"))

    def _dim(self, hc, f):
        r,g,b = int(hc[1:3],16), int(hc[3:5],16), int(hc[5:7],16)
        R,G,B = 0x16,0x16,0x1E
        return f"#{int(R+(r-R)*f):02X}{int(G+(g-G)*f):02X}{int(B+(b-B)*f):02X}"

    def _ps(self, e): self._d = (e.x, e.y)
    def _pm(self, e):
        if self._d:
            self.ox += e.x-self._d[0]; self.oy += e.y-self._d[1]
            self._d = (e.x, e.y); self.paint()
    def _scroll(self, e):
        self.zoom = max(0.15, min(6.0, self.zoom * (1.12 if e.delta > 0 else 0.89)))
        self.paint()

    def fit(self, board):
        cells = board.all_cells()
        if not cells: return
        w, h = max(1, self.winfo_width()), max(1, self.winfo_height())

        if self.view_3d:
            # In 3D mode, compute screen bounds using isometric projection
            # Try multiple zoom levels to find best fit
            self.zoom = 1.0
            self.ox = self.oy = 0.0
            for _ in range(5):
                sxs = []; sys_ = []
                for li, layer in enumerate(board.layers):
                    for c in layer.cells:
                        sx, sy = self.w2s(c.x, c.y, li)
                        sxs.append(sx); sys_.append(sy)
                if not sxs: break
                margin = 40
                sx_range = max(sxs) - min(sxs) + margin * 2
                sy_range = max(sys_) - min(sys_) + margin * 2
                scale = min(w / max(1, sx_range), h / max(1, sy_range))
                if abs(scale - 1.0) < 0.05: break
                self.zoom *= scale
                self.zoom = max(0.15, min(3.5, self.zoom))
            # Center
            sxs = []; sys_ = []
            for li, layer in enumerate(board.layers):
                for c in layer.cells:
                    sx, sy = self.w2s(c.x, c.y, li)
                    sxs.append(sx); sys_.append(sy)
            if sxs:
                cx_actual = (min(sxs) + max(sxs)) / 2
                cy_actual = (min(sys_) + max(sys_)) / 2
                self.ox += w / 2 - cx_actual
                self.oy += h / 2 - cy_actual
        else:
            xs = [c.x for c in cells]; ys = [c.y for c in cells]
            rx = max(xs) - min(xs) + 2; ry = max(ys) - min(ys) + 2
            self.zoom = min(w / (rx * self.CS) * 0.85, h / (ry * self.CS) * 0.85, 3.5)
            self.ox = -(min(xs) + max(xs)) / 2 * self.CS * self.zoom
            self.oy = (min(ys) + max(ys)) / 2 * self.CS * self.zoom

        self.paint()


# ─────────────────────────────────────────────────────────────
# Tooltip
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Edit Window — separate Toplevel for editing board layout + tiles
# ─────────────────────────────────────────────────────────────

class EditWindow(tk.Toplevel):
    """
    Popup editor for modifying board layout and tile colors.
    Opens as a separate window. Changes apply on Save, discard on Close.
    After Save, triggers re-generation + stats update in main window.
    """

    def __init__(self, master, board: Board, layers_to_edit: list[int], on_save_callback):
        super().__init__(master)
        self.title("Board Editor")
        self.geometry("900x650")
        self.configure(bg="#1A1A2E")
        self.transient(master)
        self.app = master  # reference to main App for importing layers

        # Deep copy board for editing (don't modify original until save)
        self.original_board = board
        self.edit_board = Board(board.name + " (editing)")
        for layer in board.layers:
            new_layer = Layer(layer.id)
            for c in layer.cells:
                nc = Cell(c.x, c.y, c.layer_idx)
                nc.tile_id = c.tile_id
                new_layer.cells.append(nc)
            self.edit_board.layers.append(new_layer)

        self.layers_to_edit = set(layers_to_edit) if layers_to_edit else set(range(len(board.layers)))
        self.active_layer = min(self.layers_to_edit) if self.layers_to_edit else 0
        self.tool = "add"  # "add", "erase", "paint"
        self.paint_color = 0  # tile_id to paint with
        self.on_save = on_save_callback

        n_edit = sum(len(self.edit_board.layers[i].cells) for i in self.layers_to_edit
                     if i < len(self.edit_board.layers))
        n_total = self.edit_board.total_cells()
        self.title(f"Board Editor — {len(self.layers_to_edit)} of {len(board.layers)} layers "
                    f"({n_edit}/{n_total} cells)")

        self._build_ui()
        self.after(100, self._fit_view)

    def _build_ui(self):
        # Top toolbar
        tb = tk.Frame(self, bg="#222238")
        tb.pack(fill="x", padx=4, pady=4)

        tk.Label(tb, text="Tool:", bg="#222238", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=4)
        self.tool_btns = {}
        for t, label in [("add", "Add [A]"), ("erase", "Erase [E]"), ("paint", "Paint [P]")]:
            btn = tk.Button(tb, text=label, bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                             relief="flat", command=lambda x=t: self._set_tool(x))
            btn.pack(side="left", padx=2)
            self.tool_btns[t] = btn

        tk.Label(tb, text="  Color:", bg="#222238", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=(12, 4))
        self.color_frame = tk.Frame(tb, bg="#222238")
        self.color_frame.pack(side="left")
        self.color_btns = []
        for i, (color, label, name) in enumerate(TILE_COLORS):
            btn = tk.Button(self.color_frame, bg=color, width=2, height=1, relief="flat",
                             command=lambda idx=i: self._set_paint_color(idx))
            btn.pack(side="left", padx=1)
            self.color_btns.append(btn)
            Tooltip(btn, f"Tile {i+1}: {name}")

        # Action buttons
        tk.Button(tb, text="SAVE", bg="#1B5E20", fg="#FFF", font=("Consolas", 10, "bold"),
                   relief="flat", padx=12, command=self._save).pack(side="right", padx=4)
        tk.Button(tb, text="Cancel", bg="#B71C1C", fg="#FFF", font=("Consolas", 9),
                   relief="flat", padx=8, command=self.destroy).pack(side="right", padx=2)

        # Main area: layer list + canvas
        main = tk.Frame(self, bg="#1A1A2E")
        main.pack(fill="both", expand=True)

        # Layer list (left)
        left = tk.Frame(main, bg="#1E1E2E", width=160)
        left.pack(side="left", fill="y", padx=4, pady=4)
        left.pack_propagate(False)

        tk.Label(left, text="LAYERS", bg="#1E1E2E", fg="#FFF",
                  font=("Consolas", 10, "bold")).pack(anchor="w", padx=8, pady=(8, 4))

        self.layer_list_frame = tk.Frame(left, bg="#1E1E2E")
        self.layer_list_frame.pack(fill="both", expand=True, padx=4)

        btn_frame = tk.Frame(left, bg="#1E1E2E")
        btn_frame.pack(fill="x", padx=4, pady=4)
        tk.Button(btn_frame, text="+Layer", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=self._add_layer).pack(side="left", fill="x", expand=True, padx=1)
        tk.Button(btn_frame, text="-Layer", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=self._del_layer).pack(side="left", fill="x", expand=True, padx=1)

        tk.Button(left, text="Import Layer from Main",
                   bg="#1565C0", fg="#FFF", font=("Consolas", 9, "bold"),
                   relief="flat", command=self._import_from_main
                   ).pack(fill="x", padx=4, pady=(0, 4))

        # Canvas (center)
        self.canvas = tk.Canvas(main, bg="#16161E", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_scroll)
        self.canvas.bind("<Button-3>", self._pan_start)
        self.canvas.bind("<B3-Motion>", self._pan_move)

        # Info bar
        self.info_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.info_var, bg="#16161E", fg="#778",
                  font=("Consolas", 9), anchor="w", padx=8).pack(fill="x", side="bottom")

        # Keyboard
        self.bind("<Key-a>", lambda e: self._set_tool("add"))
        self.bind("<Key-e>", lambda e: self._set_tool("erase"))
        self.bind("<Key-p>", lambda e: self._set_tool("paint"))
        for i in range(9):
            self.bind(f"<Key-{i+1}>", lambda e, idx=i: self._set_paint_color(idx))

        # Canvas state
        self._zoom = 1.0
        self._ox = self._oy = 0.0
        self._drag_start = None

        self._set_tool("add")
        self._update_layer_list()

    def _w2s(self, x, y):
        cx, cy = self.canvas.winfo_width()/2, self.canvas.winfo_height()/2
        return cx + x * 36 * self._zoom + self._ox, cy - y * 36 * self._zoom + self._oy

    def _s2w(self, sx, sy):
        cx, cy = self.canvas.winfo_width()/2, self.canvas.winfo_height()/2
        return ((sx - cx - self._ox) / (36 * self._zoom),
                -(sy - cy - self._oy) / (36 * self._zoom))

    def _snap(self, x, y, step=0.5):
        return round(x / step) * step, round(y / step) * step

    def _set_tool(self, tool):
        self.tool = tool
        for t, btn in self.tool_btns.items():
            btn.configure(bg="#4A90D9" if t == tool else "#2D2D44")

    def _set_paint_color(self, idx):
        self.paint_color = idx
        for i, btn in enumerate(self.color_btns):
            btn.configure(relief="sunken" if i == idx else "flat")

    def _update_layer_list(self):
        for w in self.layer_list_frame.winfo_children():
            w.destroy()
        for i, layer in enumerate(self.edit_board.layers):
            active = (i == self.active_layer)
            editable = (i in self.layers_to_edit)
            color = LAYER_COLORS[i % len(LAYER_COLORS)]
            row = tk.Frame(self.layer_list_frame, bg="#1E1E2E")
            row.pack(fill="x", pady=1)

            swatch = tk.Canvas(row, width=12, height=12,
                                bg=color if editable else "#333",
                                highlightthickness=0)
            swatch.pack(side="left", padx=(0, 4))

            if active:
                fg, font = "#FFF", ("Consolas", 10, "bold")
            elif editable:
                fg, font = "#AAB", ("Consolas", 10)
            else:
                fg, font = "#555", ("Consolas", 10)

            tag = "" if editable else " (locked)"
            lbl = tk.Label(row, text=f"L{i} ({len(layer.cells)}){tag}", bg="#1E1E2E",
                            fg=fg, font=font, cursor="hand2" if editable else "arrow")
            lbl.pack(side="left", fill="x")
            if editable:
                lbl.bind("<Button-1>", lambda e, idx=i: self._select_layer(idx))

    def _import_from_main(self):
        """Import a layer from main window's current board into this editor."""
        main_board = self.app.board
        if not main_board:
            messagebox.showinfo("Info", "No board loaded in main window.", parent=self)
            return
        if main_board is self.original_board and not messagebox.askyesno(
                "Same Board", "Main window has the same board.\n"
                "Load a different level in main first, or continue anyway?", parent=self):
            return

        # Show picker dialog
        dlg = tk.Toplevel(self)
        dlg.title(f"Import from: {main_board.name}")
        dlg.geometry("320x450")
        dlg.configure(bg="#1E1E2E")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text=f"Source: {main_board.name}", bg="#1E1E2E", fg="#5DADE2",
                  font=("Consolas", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
        tk.Label(dlg, text=f"{len(main_board.layers)} layers, {main_board.total_cells()} cells",
                  bg="#1E1E2E", fg="#778", font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(0, 8))

        tk.Label(dlg, text="Select layers to import:", bg="#1E1E2E", fg="#FFF",
                  font=("Consolas", 9)).pack(anchor="w", padx=12, pady=(0, 4))

        layer_vars = []
        for i, layer in enumerate(main_board.layers):
            color = LAYER_COLORS[i % len(LAYER_COLORS)]
            var = tk.BooleanVar(value=False)
            row = tk.Frame(dlg, bg="#1E1E2E")
            row.pack(fill="x", padx=12, pady=1)
            tk.Canvas(row, width=14, height=14, bg=color, highlightthickness=0).pack(side="left", padx=(0, 6))
            tk.Checkbutton(row, text=f"Layer {i}  ({len(layer.cells)} cells)",
                            variable=var, bg="#1E1E2E", fg="#AAB",
                            selectcolor="#2D2D44", font=("Consolas", 10),
                            activebackground="#1E1E2E").pack(side="left")
            layer_vars.append(var)

        # Options
        ttk.Separator(dlg, orient="horizontal").pack(fill="x", padx=12, pady=8)
        mode_var = tk.StringVar(value="append")
        tk.Label(dlg, text="Import mode:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9)).pack(anchor="w", padx=12)
        for val, txt in [("append", "Append as new layers (add on top)"),
                          ("replace", "Replace active layer"),
                          ("merge", "Merge into active layer (combine cells)")]:
            tk.Radiobutton(dlg, text=txt, variable=mode_var, value=val,
                            bg="#1E1E2E", fg="#AAB", selectcolor="#2D2D44",
                            font=("Consolas", 9), activebackground="#1E1E2E"
                            ).pack(anchor="w", padx=20)

        def do_import():
            selected = [i for i, v in enumerate(layer_vars) if v.get()]
            if not selected:
                messagebox.showinfo("Info", "No layers selected.", parent=dlg)
                return
            mode = mode_var.get()
            self._do_import_layers(main_board, selected, mode)
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg="#1E1E2E")
        btn_row.pack(fill="x", padx=12, pady=12)
        tk.Button(btn_row, text="Import", bg="#1565C0", fg="#FFF",
                   font=("Consolas", 10, "bold"), relief="flat", padx=16,
                   command=do_import).pack(side="left", padx=4)
        tk.Button(btn_row, text="Cancel", bg="#555", fg="#FFF",
                   font=("Consolas", 9), relief="flat", padx=12,
                   command=dlg.destroy).pack(side="left", padx=4)

        dlg.wait_window()

    def _do_import_layers(self, source_board, layer_indices, mode):
        """Execute the layer import."""
        for src_idx in layer_indices:
            if src_idx >= len(source_board.layers):
                continue
            src_layer = source_board.layers[src_idx]

            if mode == "append":
                # Add as new layer on top
                new_id = len(self.edit_board.layers)
                new_layer = Layer(new_id)
                for c in src_layer.cells:
                    nc = Cell(c.x, c.y, new_id)
                    nc.tile_id = c.tile_id
                    new_layer.cells.append(nc)
                self.edit_board.layers.append(new_layer)
                self.layers_to_edit.add(new_id)
                self.active_layer = new_id

            elif mode == "replace":
                # Replace current active layer's cells
                if self.active_layer < len(self.edit_board.layers):
                    target = self.edit_board.layers[self.active_layer]
                    target.cells.clear()
                    for c in src_layer.cells:
                        nc = Cell(c.x, c.y, self.active_layer)
                        nc.tile_id = c.tile_id
                        target.cells.append(nc)

            elif mode == "merge":
                # Merge cells into active layer (add new positions, skip duplicates)
                if self.active_layer < len(self.edit_board.layers):
                    target = self.edit_board.layers[self.active_layer]
                    existing = {(c.x, c.y) for c in target.cells}
                    for c in src_layer.cells:
                        if (c.x, c.y) not in existing:
                            nc = Cell(c.x, c.y, self.active_layer)
                            nc.tile_id = c.tile_id
                            target.cells.append(nc)

        self._update_layer_list()
        self._redraw()
        self._update_info()

    def _select_layer(self, idx):
        self.active_layer = idx
        self._update_layer_list()
        self._redraw()

    def _add_layer(self):
        new_id = len(self.edit_board.layers)
        self.edit_board.layers.append(Layer(new_id))
        self.active_layer = new_id
        self._update_layer_list()
        self._redraw()

    def _del_layer(self):
        if len(self.edit_board.layers) <= 1:
            return
        self.edit_board.layers.pop(self.active_layer)
        for i, l in enumerate(self.edit_board.layers):
            l.id = i
            for c in l.cells:
                c.layer_idx = i
        self.active_layer = min(self.active_layer, len(self.edit_board.layers) - 1)
        self._update_layer_list()
        self._redraw()

    def _on_click(self, event):
        wx, wy = self._s2w(event.x, event.y)
        gx, gy = self._snap(wx, wy)
        if self.active_layer >= len(self.edit_board.layers):
            return
        if self.active_layer not in self.layers_to_edit:
            return  # locked layer — can't edit
        layer = self.edit_board.layers[self.active_layer]

        if self.tool == "add":
            c = layer.add(gx, gy)
            if c:
                c.tile_id = self.paint_color
        elif self.tool == "erase":
            layer.cells = [c for c in layer.cells if not (c.x == gx and c.y == gy)]
        elif self.tool == "paint":
            for c in layer.cells:
                if c.x == gx and c.y == gy:
                    c.tile_id = self.paint_color
                    break

        self._redraw()
        self._update_layer_list()
        self._update_info()

    def _on_drag(self, event):
        if self.tool in ("add", "erase"):
            self._on_click(event)

    def _pan_start(self, e):
        self._drag_start = (e.x, e.y)

    def _pan_move(self, e):
        if self._drag_start:
            self._ox += e.x - self._drag_start[0]
            self._oy += e.y - self._drag_start[1]
            self._drag_start = (e.x, e.y)
            self._redraw()

    def _on_scroll(self, e):
        self._zoom = max(0.2, min(5.0, self._zoom * (1.1 if e.delta > 0 else 0.9)))
        self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10: return

        # Grid
        s = 36 * self._zoom
        if s > 5:
            cx, cy = w/2 + self._ox, h/2 + self._oy
            x0, y0 = cx % s, cy % s
            for x in range(int(-s), w+int(s), max(1, int(s))):
                c.create_line(x0+x, 0, x0+x, h, fill="#1E1E2A")
            for y in range(int(-s), h+int(s), max(1, int(s))):
                c.create_line(0, y0+y, w, y0+y, fill="#1E1E2A")

        # Draw all layers
        for i, layer in enumerate(self.edit_board.layers):
            active = (i == self.active_layer)
            sz = 36 * self._zoom * 0.82
            half = sz / 2
            for cell in layer.cells:
                sx, sy = self._w2s(cell.x, cell.y)
                if cell.tile_id >= 0 and cell.tile_id < len(TILE_COLORS):
                    bc = TILE_COLORS[cell.tile_id][0]
                    lb = TILE_COLORS[cell.tile_id][1]
                else:
                    bc = LAYER_COLORS[i % len(LAYER_COLORS)]
                    lb = ""
                if not active:
                    bc = self._dim(bc, 0.2)
                ol = "#FFF" if active else "#333"
                ow = 2 if active else 1
                c.create_rectangle(sx-half, sy-half, sx+half, sy+half,
                                    fill=bc, outline=ol, width=ow)
                if self._zoom > 0.5 and lb:
                    c.create_text(sx, sy, text=lb, fill="#FFF" if active else "#666",
                                   font=("Consolas", max(7, int(10*self._zoom)), "bold"))

    def _dim(self, hc, f):
        r, g, b = int(hc[1:3],16), int(hc[3:5],16), int(hc[5:7],16)
        R, G, B = 0x16, 0x16, 0x1E
        return f"#{int(R+(r-R)*f):02X}{int(G+(g-G)*f):02X}{int(B+(b-B)*f):02X}"

    def _fit_view(self):
        cells = self.edit_board.all_cells()
        if not cells: return
        xs = [c.x for c in cells]; ys = [c.y for c in cells]
        rx = max(xs)-min(xs)+2; ry = max(ys)-min(ys)+2
        w = max(1, self.canvas.winfo_width()); h = max(1, self.canvas.winfo_height())
        self._zoom = min(w/(rx*36)*0.85, h/(ry*36)*0.85, 3.0)
        self._ox = -(min(xs)+max(xs))/2 * 36 * self._zoom
        self._oy = (min(ys)+max(ys))/2 * 36 * self._zoom
        self._redraw()

    def _update_info(self):
        n = self.edit_board.total_cells()
        nl = len(self.edit_board.layers)
        self.info_var.set(f"Editing | {nl} layers | {n} cells | Tool: {self.tool} | "
                          f"Paint: {TILE_COLORS[self.paint_color][2]} | Layer: {self.active_layer}")

    def _save(self):
        """Apply edits to original board and trigger regeneration."""
        # Copy edited layers back to original
        self.original_board.layers.clear()
        for layer in self.edit_board.layers:
            new_layer = Layer(layer.id)
            for c in layer.cells:
                nc = Cell(c.x, c.y, c.layer_idx)
                nc.tile_id = c.tile_id
                new_layer.cells.append(nc)
            self.original_board.layers.append(new_layer)

        self.original_board.name = self.edit_board.name.replace(" (editing)", "")
        if self.on_save:
            self.on_save()
        self.destroy()


# ─────────────────────────────────────────────────────────────
# Play Window — test level by playing triple-match
# ─────────────────────────────────────────────────────────────

class PlayWindow(tk.Toplevel):
    """
    Playable triple-match game window.
    Mechanics match Tile Explorer:
    - Pick visible (uncovered) tiles from board
    - Tiles go to 7-slot tray, grouped by type
    - 3 matching → auto-clear
    - Tray full + no match → lose
    - All tiles cleared → win

    3 Buffs (from RE):
    1. Shuffle: randomize tile positions on board
    2. Undo: return last 3 picked tiles back to board
    3. Extra Slot: expand tray 7→8 (one-time)
    """

    TRAY_MAX = 7

    def __init__(self, master, board: Board):
        super().__init__(master)
        self.title(f"Play: {board.name}")
        self.geometry("750x700")
        self.configure(bg="#0D0D1A")

        # Deep copy board
        self.board = Board(board.name)
        for layer in board.layers:
            nl = Layer(layer.id)
            for c in layer.cells:
                nc = Cell(c.x, c.y, c.layer_idx)
                nc.tile_id = c.tile_id
                nl.cells.append(nc)
            self.board.layers.append(nl)

        # Save original tile_ids for restart (shuffle modifies them in-place)
        self._original_tile_ids = {id(c): c.tile_id for c in self.board.all_cells()}
        self.show_coords = False  # toggle for coordinate display

        # Game state
        self.active = {id(c) for c in self.board.all_cells()}
        self.tray = []  # list of tile_id values
        self.moves = 0
        self.cleared = 0
        self.total_tiles = len(self.active)
        self.game_over = False
        self.won = False
        self.history = []  # for undo: list of (cell_id, tile_id)

        # Buffs
        self.buff_shuffle = 3
        self.buff_undo = 3
        self.buff_extra = 1
        self.tray_max = self.TRAY_MAX

        # Build visibility
        self.vis = self._build_vis()
        self.cell_map = {id(c): c for c in self.board.all_cells()}

        self._build_ui()
        self.after(100, self._fit)

    def _build_vis(self):
        blocked_by = {}
        for c in self.board.all_cells():
            blocked_by[id(c)] = set()
        for i in range(len(self.board.layers)):
            for j in range(i + 1, len(self.board.layers)):
                for uc in self.board.layers[j].cells:
                    for lc in self.board.layers[i].cells:
                        if abs(uc.x - lc.x) < 1.0 and abs(uc.y - lc.y) < 1.0:
                            blocked_by[id(lc)].add(id(uc))
        return blocked_by

    def _get_pickable(self):
        result = []
        for c in self.board.all_cells():
            cid = id(c)
            if cid not in self.active:
                continue
            blockers = self.vis.get(cid, set())
            if not blockers.intersection(self.active):
                result.append(c)
        return result

    def _build_ui(self):
        # Top info bar
        info = tk.Frame(self, bg="#111128")
        info.pack(fill="x", padx=4, pady=4)

        self.lbl_moves = tk.Label(info, text="Moves: 0", bg="#111128", fg="#AAB",
                                    font=("Consolas", 11))
        self.lbl_moves.pack(side="left", padx=8)
        self.lbl_remain = tk.Label(info, text=f"Remaining: {self.total_tiles}",
                                     bg="#111128", fg="#AAB", font=("Consolas", 11))
        self.lbl_remain.pack(side="left", padx=8)
        self.lbl_status = tk.Label(info, text="Playing...", bg="#111128", fg="#5DADE2",
                                     font=("Consolas", 12, "bold"))
        self.lbl_status.pack(side="right", padx=8)

        # Board canvas
        self.canvas = tk.Canvas(self, bg="#0D0D1A", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Button-3>", self._pan_s)
        self.canvas.bind("<B3-Motion>", self._pan_m)
        self.canvas.bind("<MouseWheel>", self._scroll)

        # Tray + Buffs bar
        bottom = tk.Frame(self, bg="#111128")
        bottom.pack(fill="x", padx=4, pady=(0, 4))

        # Tray display
        self.tray_canvas = tk.Canvas(bottom, bg="#0A0A18", height=50, highlightthickness=0)
        self.tray_canvas.pack(fill="x", padx=4, pady=4)

        # Buff buttons
        buff_frame = tk.Frame(bottom, bg="#111128")
        buff_frame.pack(fill="x", padx=4, pady=(0, 4))

        self.btn_shuffle = tk.Button(buff_frame, text=f"Shuffle ({self.buff_shuffle})",
                                       bg="#1565C0", fg="#FFF", font=("Consolas", 10, "bold"),
                                       relief="flat", padx=12, command=self._use_shuffle)
        self.btn_shuffle.pack(side="left", padx=4, fill="x", expand=True)

        self.btn_undo = tk.Button(buff_frame, text=f"Undo ({self.buff_undo})",
                                    bg="#6A1B9A", fg="#FFF", font=("Consolas", 10, "bold"),
                                    relief="flat", padx=12, command=self._use_undo)
        self.btn_undo.pack(side="left", padx=4, fill="x", expand=True)

        self.btn_extra = tk.Button(buff_frame, text=f"+1 Slot ({self.buff_extra})",
                                     bg="#E65100", fg="#FFF", font=("Consolas", 10, "bold"),
                                     relief="flat", padx=12, command=self._use_extra)
        self.btn_extra.pack(side="left", padx=4, fill="x", expand=True)

        tk.Button(buff_frame, text="Restart", bg="#333", fg="#AAB", font=("Consolas", 9),
                   relief="flat", padx=8, command=self._restart).pack(side="right", padx=4)

        self.btn_coords = tk.Button(buff_frame, text="Coords: OFF",
                                     bg="#333", fg="#AAB", font=("Consolas", 9),
                                     relief="flat", padx=8, command=self._toggle_coords)
        self.btn_coords.pack(side="right", padx=4)

        # Canvas state
        self._zoom = 1.0
        self._ox = self._oy = 0.0
        self._drag = None

        self._paint()

    def _w2s(self, x, y, li=0):
        cx, cy = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        return cx + x * 36 * self._zoom + self._ox, cy - y * 36 * self._zoom + self._oy

    def _s2w(self, sx, sy):
        cx, cy = self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2
        return ((sx - cx - self._ox) / (36 * self._zoom),
                -(sy - cy - self._oy) / (36 * self._zoom))

    def _fit(self):
        cells = self.board.all_cells()
        if not cells:
            return
        xs = [c.x for c in cells]; ys = [c.y for c in cells]
        rx = max(xs) - min(xs) + 2; ry = max(ys) - min(ys) + 2
        w = max(1, self.canvas.winfo_width()); h = max(1, self.canvas.winfo_height())
        self._zoom = min(w / (rx * 36) * 0.85, h / (ry * 36) * 0.85, 3.0)
        self._ox = -(min(xs) + max(xs)) / 2 * 36 * self._zoom
        self._oy = (min(ys) + max(ys)) / 2 * 36 * self._zoom
        self._paint()

    def _paint(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 10:
            return

        pickable = set(id(x) for x in self._get_pickable())

        # Draw layers bottom to top
        for li, layer in enumerate(self.board.layers):
            sz = 36 * self._zoom * 1.0  # full grid size — match game (4 corners cover back tile)
            half = sz / 2
            for cell in layer.cells:
                cid = id(cell)
                if cid not in self.active:
                    continue  # already removed

                sx, sy = self._w2s(cell.x, cell.y)
                is_pick = cid in pickable

                if cell.tile_id >= 0 and cell.tile_id < len(TILE_COLORS):
                    bc, lb, _ = TILE_COLORS[cell.tile_id]
                else:
                    bc = LAYER_COLORS[li % len(LAYER_COLORS)]
                    lb = ""

                if is_pick:
                    fill = bc
                    ol = "#FFF"
                    ow = 2
                else:
                    fill = self._dim(bc, 0.35)
                    ol = "#333"
                    ow = 1

                r = max(2, 4 * self._zoom)
                pts = [sx-half+r, sy-half, sx+half-r, sy-half,
                       sx+half, sy-half, sx+half, sy-half+r,
                       sx+half, sy+half-r, sx+half, sy+half,
                       sx+half-r, sy+half, sx-half+r, sy+half,
                       sx-half, sy+half, sx-half, sy+half-r,
                       sx-half, sy-half+r, sx-half, sy-half]
                c.create_polygon(pts, smooth=True, fill=fill, outline=ol, width=ow)

                if self._zoom > 0.4 and lb:
                    c.create_text(sx, sy, text=lb,
                                   fill="#FFF" if is_pick else "#666",
                                   font=("Segoe UI Symbol", max(18, int(28 * self._zoom)), "bold"))

                # Coordinate label on top-left of each visible (pickable) tile (toggleable)
                if self.show_coords and is_pick and self._zoom > 0.5:
                    coord_txt = f"L{cell.layer_idx}({cell.x:g},{cell.y:g})"
                    c.create_text(sx - half + 2, sy - half + 2, text=coord_txt,
                                   anchor="nw", fill="#FFD700",
                                   font=("Consolas", max(6, int(7 * self._zoom))))

        self._paint_tray()

    def _paint_tray(self):
        tc = self.tray_canvas
        tc.delete("all")
        tw = tc.winfo_width()
        th = tc.winfo_height()
        if tw < 10:
            return

        slot_w = min(45, (tw - 20) // self.tray_max)
        start_x = (tw - slot_w * self.tray_max) // 2

        # Draw slots
        for i in range(self.tray_max):
            x = start_x + i * slot_w
            tc.create_rectangle(x + 2, 5, x + slot_w - 2, th - 5,
                                 fill="#161630", outline="#333", width=1)

        # Draw tiles in tray
        for i, tid in enumerate(self.tray):
            x = start_x + i * slot_w
            if tid >= 0 and tid < len(TILE_COLORS):
                bc, lb, _ = TILE_COLORS[tid]
            else:
                bc, lb = "#888", "?"
            tc.create_rectangle(x + 4, 7, x + slot_w - 4, th - 7,
                                 fill=bc, outline="#FFF", width=1)
            tc.create_text(x + slot_w // 2, th // 2, text=lb,
                            fill="#FFF", font=("Consolas", 12, "bold"))

        # Slot count label
        tc.create_text(tw - 8, th // 2, text=f"{len(self.tray)}/{self.tray_max}",
                        fill="#556", font=("Consolas", 9), anchor="e")

    def _dim(self, hc, f):
        r, g, b = int(hc[1:3], 16), int(hc[3:5], 16), int(hc[5:7], 16)
        R, G, B = 0x0D, 0x0D, 0x1A
        return f"#{int(R+(r-R)*f):02X}{int(G+(g-G)*f):02X}{int(B+(b-B)*f):02X}"

    # ─── Input ───

    def _on_click(self, event):
        if self.game_over:
            return
        wx, wy = self._s2w(event.x, event.y)

        # Find closest pickable cell
        pickable = self._get_pickable()
        if not pickable:
            return

        best = None
        best_dist = 999
        for cell in pickable:
            dx = cell.x - wx
            dy = cell.y - wy
            d = dx * dx + dy * dy
            if d < best_dist and d < 1.0:  # within 1 unit
                best = cell
                best_dist = d

        if best is None:
            return

        self._pick_tile(best)

    def _pick_tile(self, cell):
        """Pick a tile: remove from board, add to tray, check matches."""
        cid = id(cell)
        self.active.discard(cid)
        self.moves += 1

        # Add to history for undo
        self.history.append((cid, cell.tile_id))

        # Insert into tray with TYPE GROUPING (same type adjacent)
        tid = cell.tile_id
        inserted = False
        for i in range(len(self.tray)):
            if self.tray[i] == tid:
                self.tray.insert(i + 1, tid)
                inserted = True
                break
        if not inserted:
            self.tray.append(tid)

        # Clear all triplets
        self._clear_tray_matches()

        # Check win
        if not self.active:
            self.won = True
            self.game_over = True
            self.lbl_status.config(text="WIN!", fg="#58D68D")

        # Check lose: tray full and no match
        elif len(self.tray) >= self.tray_max:
            counts = {}
            for t in self.tray:
                counts[t] = counts.get(t, 0) + 1
            if not any(v >= 3 for v in counts.values()):
                self.game_over = True
                self.lbl_status.config(text="GAME OVER", fg="#E74C3C")

        self._update_info()
        self._paint()

    def _clear_tray_matches(self):
        """Clear all matching triplets from tray."""
        changed = True
        while changed:
            changed = False
            counts = {}
            for t in self.tray:
                counts[t] = counts.get(t, 0) + 1
            for t, cnt in counts.items():
                if cnt >= 3:
                    new_tray = []
                    removed = 0
                    for tv in self.tray:
                        if tv == t and removed < 3:
                            removed += 1
                            self.cleared += 1
                        else:
                            new_tray.append(tv)
                    self.tray = new_tray
                    changed = True
                    break

    # ─── Buffs ───

    def _pick_forced_types(self, candidate_types, type_counts, tray_counts, tray_free, max_types=2):
        """Select up to max_types types to force onto pickable cells.

        Absolute priority for types already on tray:
        1. Types on tray with 2 copies (need 1 pick) — sorted by most board copies
        2. Types on tray with 1 copy (need 2 picks) — sorted by most board copies
        3. Only if slots remain: types NOT on tray — sorted by most board copies

        Safety: only pick if picks needed <= effective_free (accounting for
        clears from previously chosen types).
        """
        chosen = []
        used = set()
        effective_free = tray_free

        # Phase 1: types already on tray, ordered by on_tray desc then board copies desc
        tray_candidates = [t for t in candidate_types if tray_counts.get(t, 0) >= 1]
        tray_candidates.sort(key=lambda t: (-tray_counts.get(t, 0), -type_counts[t]))

        for t in tray_candidates:
            if len(chosen) >= max_types:
                break
            if t in used:
                continue
            needed = 3 - tray_counts.get(t, 0)
            if needed > effective_free:
                continue
            chosen.append(t)
            used.add(t)
            effective_free = effective_free - needed + 3

        # Phase 2: types NOT on tray, only if slots remain
        if len(chosen) < max_types:
            non_tray = [t for t in candidate_types if tray_counts.get(t, 0) == 0]
            non_tray.sort(key=lambda t: -type_counts[t])

            for t in non_tray:
                if len(chosen) >= max_types:
                    break
                if t in used:
                    continue
                needed = 3
                if needed > effective_free:
                    continue
                chosen.append(t)
                used.add(t)
                effective_free = effective_free - needed + 3

        return chosen

    def _use_shuffle(self):
        """Buff 1: Shuffle all remaining tiles on board.

        Dynamic triple count based on tray state:
        - Tray has 3+ distinct types → force up to 3 triples
        - Otherwise → force up to 2 triples
        Priority: types already on tray first, then types with most copies.
        Safety: won't force a triple if picks needed exceed remaining tray slots.
        """
        if self.game_over or self.buff_shuffle <= 0:
            return
        self.buff_shuffle -= 1

        active_cells = [self.cell_map[cid] for cid in self.active]
        tile_ids = [c.tile_id for c in active_cells]

        pickable_cells = self._get_pickable()
        pickable_count = len(pickable_cells)

        type_counts = {}
        for tid in tile_ids:
            type_counts[tid] = type_counts.get(tid, 0) + 1

        tray_counts = {}
        for tid in self.tray:
            tray_counts[tid] = tray_counts.get(tid, 0) + 1
        tray_free = self.tray_max - len(self.tray)

        # Candidate types: for tray types, only need (3 - on_tray) copies on board
        # For non-tray types, need >= 3 copies on board
        candidate_types = []
        for t, c in type_counts.items():
            on_tray = tray_counts.get(t, 0)
            need_on_board = 3 - on_tray
            if c >= need_on_board and need_on_board >= 1:
                candidate_types.append(t)

        # Dynamic max: if tray has 3+ distinct types, try to force 3 triples
        tray_distinct = len(tray_counts)
        target_triples = 3 if tray_distinct >= 3 else 2
        max_triples = min(target_triples, pickable_count // 3)
        chosen_types = self._pick_forced_types(
            candidate_types, type_counts, tray_counts, tray_free, max_triples)

        if chosen_types:
            # Calculate how many copies to force per type
            force_counts = {}
            total_forced = 0
            for ct in chosen_types:
                on_tray = tray_counts.get(ct, 0)
                force = 3 - on_tray  # only force what's needed to complete triple
                force_counts[ct] = force
                total_forced += force

            if pickable_count >= total_forced:
                forced_pickable = random.sample(pickable_cells, total_forced)
                forced_ids = set()

                remaining_ids = list(tile_ids)
                idx = 0
                for ct in chosen_types:
                    fc = force_counts[ct]
                    for j in range(fc):
                        forced_ids.add(id(forced_pickable[idx]))
                        idx += 1
                    # Remove fc copies from remaining pool
                    for _ in range(fc):
                        remaining_ids.remove(ct)
                random.shuffle(remaining_ids)

                rem_iter = iter(remaining_ids)
                for c in active_cells:
                    if id(c) in forced_ids:
                        continue
                    else:
                        c.tile_id = next(rem_iter)

                idx = 0
                for ct in chosen_types:
                    fc = force_counts[ct]
                    for j in range(fc):
                        forced_pickable[idx].tile_id = ct
                        idx += 1
        else:
            random.shuffle(tile_ids)
            for c, tid in zip(active_cells, tile_ids):
                c.tile_id = tid

        self.btn_shuffle.config(text=f"Shuffle ({self.buff_shuffle})")
        self._paint()

    def _use_undo(self):
        """Buff 2: Return last 1 tile from tray back to board."""
        if self.game_over or self.buff_undo <= 0 or not self.tray:
            return
        self.buff_undo -= 1

        tid = self.tray.pop()
        for hi in range(len(self.history) - 1, -1, -1):
            h_cid, h_tid = self.history[hi]
            if h_tid == tid and h_cid not in self.active:
                self.active.add(h_cid)
                self.history.pop(hi)
                break

        self.btn_undo.config(text=f"Undo ({self.buff_undo})")
        self.game_over = False
        self.lbl_status.config(text="Playing...", fg="#5DADE2")
        self._update_info()
        self._paint()

    def _use_extra(self):
        """Buff 3: Expand tray by 1 slot (7→8)."""
        if self.game_over or self.buff_extra <= 0:
            return
        self.buff_extra -= 1
        self.tray_max += 1

        self.btn_extra.config(text=f"+1 Slot ({self.buff_extra})")
        # Un-game-over if we were stuck
        if self.game_over and not self.won:
            self.game_over = False
            self.lbl_status.config(text="Playing...", fg="#5DADE2")
        self._paint()

    def _toggle_coords(self):
        """Toggle coordinate labels on tiles."""
        self.show_coords = not self.show_coords
        self.btn_coords.config(text=f"Coords: {'ON' if self.show_coords else 'OFF'}",
                                fg="#FFD700" if self.show_coords else "#AAB")
        self._paint()

    def _restart(self):
        """Reset to initial state."""
        # Restore original tile_ids (shuffle may have changed them)
        for c in self.board.all_cells():
            c.tile_id = self._original_tile_ids[id(c)]
        self.active = {id(c) for c in self.board.all_cells()}
        self.tray = []
        self.moves = 0
        self.cleared = 0
        self.game_over = False
        self.won = False
        self.history = []
        self.buff_shuffle = 3
        self.buff_undo = 3
        self.buff_extra = 1
        self.tray_max = self.TRAY_MAX
        self.btn_shuffle.config(text=f"Shuffle ({self.buff_shuffle})")
        self.btn_undo.config(text=f"Undo ({self.buff_undo})")
        self.btn_extra.config(text=f"+1 Slot ({self.buff_extra})")
        self.lbl_status.config(text="Playing...", fg="#5DADE2")
        self._update_info()
        self._paint()

    # ─── Navigation ───

    def _pan_s(self, e): self._drag = (e.x, e.y)
    def _pan_m(self, e):
        if self._drag:
            self._ox += e.x - self._drag[0]
            self._oy += e.y - self._drag[1]
            self._drag = (e.x, e.y)
            self._paint()
    def _scroll(self, e):
        self._zoom = max(0.2, min(5.0, self._zoom * (1.1 if e.delta > 0 else 0.9)))
        self._paint()

    def _update_info(self):
        remain = len(self.active)
        self.lbl_moves.config(text=f"Moves: {self.moves}")
        self.lbl_remain.config(text=f"Remaining: {remain}/{self.total_tiles}")


# ─────────────────────────────────────────────────────────────
# Level Finder / Order Window — advanced search with retry generation
# ─────────────────────────────────────────────────────────────

class FinderWindow(tk.Toplevel):
    """
    Advanced level search: scan boards, filter by detailed criteria,
    retry generation up to N times per board to find matching tile configs.
    """

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Level Finder")
        self.geometry("900x720")
        self.configure(bg="#1A1A2E")
        self.transient(app)

        self.results = []
        self.running = False
        self._build_ui()

    def _rng(self, parent, label, lo_def, hi_def, lo=0, hi=9999, w=5):
        """Helper: create a labeled min-max range row."""
        r = tk.Frame(parent, bg="#1E1E2E")
        r.pack(fill="x", padx=8, pady=2)
        tk.Label(r, text=label, bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9), width=16, anchor="e").pack(side="left")
        v_lo = tk.IntVar(value=lo_def)
        v_hi = tk.IntVar(value=hi_def)
        tk.Spinbox(r, from_=lo, to=hi, textvariable=v_lo, width=w,
                    bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)
        tk.Label(r, text="to", bg="#1E1E2E", fg="#556", font=("Consolas", 9)).pack(side="left", padx=3)
        tk.Spinbox(r, from_=lo, to=hi, textvariable=v_hi, width=w,
                    bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)
        return v_lo, v_hi

    def _build_ui(self):
        # Scrollable criteria area
        outer = tk.Frame(self, bg="#1E1E2E")
        outer.pack(fill="x", padx=4, pady=4)

        tk.Label(outer, text="Level Order / Advanced Search", bg="#1E1E2E", fg="#5DADE2",
                  font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=8, pady=(4, 6))

        # ── Source selection ──
        sf = tk.LabelFrame(outer, text="Source", bg="#1E1E2E", fg="#8899AA",
                            font=("Consolas", 9, "bold"), padx=6, pady=4)
        sf.pack(fill="x", padx=8, pady=2)

        self.v_src = tk.StringVar(value="all")
        src_row = tk.Frame(sf, bg="#1E1E2E")
        src_row.pack(fill="x")
        for val, txt in [("all", "All files"), ("selected", "Selected files only")]:
            tk.Radiobutton(src_row, text=txt, variable=self.v_src, value=val,
                            bg="#1E1E2E", fg="#AAB", selectcolor="#2D2D44",
                            font=("Consolas", 9), activebackground="#1E1E2E"
                            ).pack(side="left", padx=4)

        # File multi-select listbox
        self.file_list = tk.Listbox(sf, bg="#16161E", fg="#AAB", font=("Consolas", 9),
                                      height=4, selectmode="extended", borderwidth=0)
        for f in list_level_files():
            self.file_list.insert("end", f)
        self.file_list.pack(fill="x", pady=4)

        r_scope = tk.Frame(sf, bg="#1E1E2E")
        r_scope.pack(fill="x")
        tk.Label(r_scope, text="Boards per file:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9)).pack(side="left")
        self.v_bpf = tk.IntVar(value=10)
        tk.Spinbox(r_scope, from_=1, to=100, textvariable=self.v_bpf, width=5,
                    bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=4)

        # ── Board criteria ──
        bf = tk.LabelFrame(outer, text="Board Shape", bg="#1E1E2E", fg="#8899AA",
                            font=("Consolas", 9, "bold"), padx=6, pady=4)
        bf.pack(fill="x", padx=8, pady=2)

        self.v_cells = self._rng(bf, "Total Cells:", 20, 300, 1, 500)
        self.v_layers = self._rng(bf, "Layers:", 1, 15, 1, 20)

        # ── Generation params ──
        gf = tk.LabelFrame(outer, text="Tile Generation", bg="#1E1E2E", fg="#8899AA",
                            font=("Consolas", 9, "bold"), padx=6, pady=4)
        gf.pack(fill="x", padx=8, pady=2)

        r_cc = tk.Frame(gf, bg="#1E1E2E")
        r_cc.pack(fill="x", padx=8, pady=2)
        tk.Label(r_cc, text="Color Count:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9), width=16, anchor="e").pack(side="left")
        self.v_cc = tk.IntVar(value=4)
        tk.Spinbox(r_cc, from_=2, to=25, textvariable=self.v_cc, width=5,
                    bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)

        r_retry = tk.Frame(gf, bg="#1E1E2E")
        r_retry.pack(fill="x", padx=8, pady=2)
        tk.Label(r_retry, text="Retries/board:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9), width=16, anchor="e").pack(side="left")
        self.v_retries = tk.IntVar(value=10)
        tk.Spinbox(r_retry, from_=1, to=500, textvariable=self.v_retries, width=5,
                    bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)
        tk.Label(r_retry, text="(re-generate tiles until criteria met)", bg="#1E1E2E",
                  fg="#556", font=("Consolas", 8)).pack(side="left", padx=6)

        # Custom triple counts
        self.v_finder_custom_triples = tk.BooleanVar(value=False)
        ct_cb = tk.Checkbutton(gf, text="Custom Triple Counts", variable=self.v_finder_custom_triples,
                                bg="#1E1E2E", fg="#AAB", selectcolor="#2D2D44",
                                font=("Consolas", 9), activebackground="#1E1E2E",
                                command=self._toggle_finder_triples)
        ct_cb.pack(anchor="w", padx=8, pady=1)

        self._finder_triple_frame = tk.Frame(gf, bg="#1E1E2E")
        self._finder_triple_frame.pack(fill="x", padx=8)
        self._finder_triple_vars = []
        self._finder_triple_widgets = []

        # ── Solvability criteria ──
        sf2 = tk.LabelFrame(outer, text="Solvability Criteria", bg="#1E1E2E", fg="#8899AA",
                             font=("Consolas", 9, "bold"), padx=6, pady=4)
        sf2.pack(fill="x", padx=8, pady=2)

        r_sims = tk.Frame(sf2, bg="#1E1E2E")
        r_sims.pack(fill="x", padx=8, pady=2)
        tk.Label(r_sims, text="Simulations:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9), width=16, anchor="e").pack(side="left")
        self.v_sims = tk.IntVar(value=100)
        tk.Spinbox(r_sims, from_=20, to=2000, increment=20, textvariable=self.v_sims,
                    width=5, bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)

        self.v_solve = self._rng(sf2, "Solve Rate %:", 30, 100, 0, 100)
        self.v_dead = self._rng(sf2, "Deadlock Rate %:", 0, 70, 0, 100)
        self.v_minmv = self._rng(sf2, "Min Moves:", 10, 999, 0, 999)
        self.v_avgmv = self._rng(sf2, "Avg Moves:", 20, 999, 0, 999)
        self.v_comp = self._rng(sf2, "Complexity Score:", 0, 100, 0, 100)

        # Complexity label filter
        r_cl = tk.Frame(sf2, bg="#1E1E2E")
        r_cl.pack(fill="x", padx=8, pady=2)
        tk.Label(r_cl, text="Difficulty:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 9), width=16, anchor="e").pack(side="left")
        self.v_diff = tk.StringVar(value="Any")
        for v in ["Any", "Very Easy", "Easy", "Medium", "Hard", "Very Hard", "Extreme"]:
            tk.Radiobutton(r_cl, text=v, variable=self.v_diff, value=v,
                            bg="#1E1E2E", fg="#AAB", selectcolor="#2D2D44",
                            font=("Consolas", 8), activebackground="#1E1E2E"
                            ).pack(side="left", padx=1)

        # ── Scoring Weights ──
        wf = tk.LabelFrame(outer, text="Scoring Weights", bg="#1E1E2E", fg="#8899AA",
                            font=("Consolas", 9, "bold"), padx=6, pady=4)
        wf.pack(fill="x", padx=8, pady=2)

        saved_w = load_scoring_weights()
        self.w_X = tk.DoubleVar(value=saved_w.get("X", 1.0))
        self.w_Y = tk.DoubleVar(value=saved_w.get("Y", 1.0))
        self.w_Z = tk.DoubleVar(value=saved_w.get("Z", 1.0))
        self.w_K = tk.DoubleVar(value=saved_w.get("K", 0.5))

        wr = tk.Frame(wf, bg="#1E1E2E")
        wr.pack(fill="x")
        for label, var in [("X(Layout)", self.w_X), ("Y(Inter)", self.w_Y),
                           ("Z(Intra)", self.w_Z), ("K(Cover)", self.w_K)]:
            tk.Label(wr, text=label, bg="#1E1E2E", fg="#AAB",
                     font=("Consolas", 8)).pack(side="left", padx=1)
            tk.Spinbox(wr, from_=0.0, to=10.0, increment=0.1, textvariable=var, width=4,
                       bg="#16161E", fg="#AAB", font=("Consolas", 8)).pack(side="left", padx=1)

        # New score filters
        self.v_new_score = self._rng(wf, "Final Score:", 0, 9999, 0, 9999)
        self.v_inter_range = self._rng(wf, "Inter-Group:", 0, 9999, 0, 9999)
        self.v_intra_range = self._rng(wf, "Intra-Group:", 0, 9999, 0, 9999)

        # Samples per board (for min/max)
        r_samples = tk.Frame(wf, bg="#1E1E2E")
        r_samples.pack(fill="x", padx=8, pady=2)
        tk.Label(r_samples, text="Samples/board:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 8), width=14, anchor="e").pack(side="left")
        self.v_samples = tk.IntVar(value=1)
        tk.Spinbox(r_samples, from_=1, to=500, textvariable=self.v_samples, width=4,
                    bg="#16161E", fg="#AAB", font=("Consolas", 8)).pack(side="left", padx=2)
        tk.Label(r_samples, text="(>1 = run N gens, report min/max)", bg="#1E1E2E",
                  fg="#556", font=("Consolas", 7)).pack(side="left", padx=4)

        # ── Action buttons ──
        act = tk.Frame(outer, bg="#1E1E2E")
        act.pack(fill="x", padx=8, pady=6)

        self.btn_search = tk.Button(act, text="SEARCH", bg="#1B5E20", fg="#FFF",
                                      font=("Consolas", 11, "bold"), relief="flat", padx=20,
                                      command=self._start_search)
        self.btn_search.pack(side="left", padx=4)

        self.btn_stop = tk.Button(act, text="STOP", bg="#B71C1C", fg="#FFF",
                                    font=("Consolas", 10, "bold"), relief="flat", padx=12,
                                    command=self._stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        # Export dropdown
        exp_btn = tk.Menubutton(act, text="Export", bg="#1565C0", fg="#FFF",
                                  font=("Consolas", 10, "bold"), relief="flat", padx=10)
        exp_menu = tk.Menu(exp_btn, tearoff=0)
        exp_menu.add_command(label="Export Summary (JSON)", command=lambda: self._export("json"))
        exp_menu.add_command(label="Export Summary (CSV)", command=lambda: self._export("csv"))
        exp_menu.add_separator()
        exp_menu.add_command(label="Export All Boards (JSON per board)",
                              command=lambda: self._export("boards_json"))
        exp_menu.add_command(label="Export All Boards (single JSON)",
                              command=lambda: self._export("boards_single"))
        exp_menu.add_separator()
        exp_menu.add_command(label="Export Selected Row", command=lambda: self._export("selected"))
        exp_btn.config(menu=exp_menu)
        exp_btn.pack(side="left", padx=4)

        self.lbl_progress = tk.Label(act, text="", bg="#1E1E2E", fg="#778",
                                       font=("Consolas", 9))
        self.lbl_progress.pack(side="left", padx=8)

        # ── Results table ──
        tk.Frame(self, bg="#333", height=1).pack(fill="x", padx=4)

        rf = tk.Frame(self, bg="#1A1A2E")
        rf.pack(fill="both", expand=True, padx=4, pady=4)

        cols = ("file", "board", "cells", "layers", "gen", "solve", "dead",
                "minmv", "avgmv", "score", "label",
                "n_layout", "n_inter", "n_intra", "n_cover", "n_final",
                "ig_min", "ig_max", "ng_min", "ng_max")
        self.tree = ttk.Treeview(rf, columns=cols, show="headings", height=12)

        hdrs = [("file", "File", 90), ("board", "#", 35), ("cells", "Cells", 45),
                ("layers", "Lyr", 35), ("gen", "Gen#", 35), ("solve", "Solve%", 55),
                ("dead", "Dead%", 55), ("minmv", "MinMv", 50), ("avgmv", "AvgMv", 50),
                ("score", "Score", 45), ("label", "Difficulty", 75),
                ("n_layout", "Layout", 50), ("n_inter", "Inter", 50),
                ("n_intra", "Intra", 50), ("n_cover", "Cvr100", 45),
                ("n_final", "NewScore", 60),
                ("ig_min", "IgMin", 45), ("ig_max", "IgMax", 45),
                ("ng_min", "NgMin", 45), ("ng_max", "NgMax", 45)]
        for col, txt, w in hdrs:
            self.tree.heading(col, text=txt, command=lambda c=col: self._sort(c))
            self.tree.column(col, width=w, minwidth=30)

        scroll = ttk.Scrollbar(rf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self._on_select)

        # Action buttons below table
        act2 = tk.Frame(self, bg="#1A1A2E")
        act2.pack(fill="x", padx=8, pady=(0, 4))
        tk.Button(act2, text="Play Selected", bg="#1B5E20", fg="#FFF",
                   font=("Consolas", 10, "bold"), relief="flat", padx=12,
                   command=self._play_selected).pack(side="left", padx=4)
        tk.Button(act2, text="Pin Selected", bg="#6A1B9A", fg="#FFF",
                   font=("Consolas", 9), relief="flat", padx=8,
                   command=self._pin_selected).pack(side="left", padx=4)
        tk.Button(act2, text="Pin All Results", bg="#4A148C", fg="#FFF",
                   font=("Consolas", 9), relief="flat", padx=8,
                   command=self._pin_all).pack(side="left", padx=4)
        tk.Label(act2, text="Dbl-click=Load | Headers=Sort",
                  bg="#1A1A2E", fg="#445", font=("Consolas", 8)).pack(side="right", padx=8)

        self._sort_reverse = {}

    def _toggle_finder_triples(self):
        for w in self._finder_triple_widgets:
            w.destroy()
        self._finder_triple_widgets.clear()
        self._finder_triple_vars.clear()

        if not self.v_finder_custom_triples.get():
            return

        cc = self.v_cc.get()
        for t in range(cc):
            row = tk.Frame(self._finder_triple_frame, bg="#1E1E2E")
            row.pack(fill="x", pady=1)
            self._finder_triple_widgets.append(row)
            color = TILE_COLORS[t][0] if t < len(TILE_COLORS) else "#888"
            name = TILE_COLORS[t][2] if t < len(TILE_COLORS) else f"Type{t}"
            swatch = tk.Frame(row, bg=color, width=12, height=12)
            swatch.pack(side="left", padx=(2, 4))
            swatch.pack_propagate(False)
            tk.Label(row, text=f"{name}:", bg="#1E1E2E", fg="#AAB",
                     font=("Consolas", 8), width=7).pack(side="left")
            var = tk.IntVar(value=5)
            tk.Spinbox(row, from_=0, to=200, textvariable=var, width=4,
                       bg="#16161E", fg="#AAB", font=("Consolas", 8)).pack(side="left", padx=2)
            self._finder_triple_vars.append(var)

    def _start_search(self):
        self.running = True
        self.btn_search.config(state="disabled")
        self.btn_stop.config(state="normal")

        self.results.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Gather params once
        files = list_level_files()
        if self.v_src.get() == "selected":
            sel = self.file_list.curselection()
            if sel:
                files = [self.file_list.get(i) for i in sel]

        bpf = self.v_bpf.get()

        # Build work queue: list of (fname, board_idx)
        self._work = []
        for fname in files:
            cnt = get_board_count(fname)
            for bi in range(min(cnt, bpf)):
                self._work.append((fname, bi))

        self._work_idx = 0
        self._found = 0
        self._params = {
            "c": (self.v_cells[0].get(), self.v_cells[1].get()),
            "l": (self.v_layers[0].get(), self.v_layers[1].get()),
            "s": (self.v_solve[0].get(), self.v_solve[1].get()),
            "d": (self.v_dead[0].get(), self.v_dead[1].get()),
            "mm": (self.v_minmv[0].get(), self.v_minmv[1].get()),
            "am": (self.v_avgmv[0].get(), self.v_avgmv[1].get()),
            "sc": (self.v_comp[0].get(), self.v_comp[1].get()),
            "diff": self.v_diff.get(),
            "cc": self.v_cc.get(),
            "retries": self.v_retries.get(),
            "sims": self.v_sims.get(),
            "ns": (self.v_new_score[0].get(), self.v_new_score[1].get()),
            "ig": (self.v_inter_range[0].get(), self.v_inter_range[1].get()),
            "ng": (self.v_intra_range[0].get(), self.v_intra_range[1].get()),
            "samples": self.v_samples.get(),
            "ct": {i: v.get() for i, v in enumerate(self._finder_triple_vars)}
                  if self.v_finder_custom_triples.get() and self._finder_triple_vars else None,
        }

        # Start incremental processing
        self.after(10, self._process_next)

    def _stop(self):
        self.running = False
        self.btn_search.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_progress.config(
            text=f"Stopped: {self._found} matched / {self._work_idx} scanned")

    def _process_next(self):
        """Process ONE board per call, then yield to UI via after()."""
        if not self.running or self._work_idx >= len(self._work):
            # Done
            self.running = False
            self.btn_search.config(state="normal")
            self.btn_stop.config(state="disabled")
            self.lbl_progress.config(
                text=f"Done: {self._found} matched / {self._work_idx} scanned")
            return

        fname, bi = self._work[self._work_idx]
        self._work_idx += 1
        total = len(self._work)
        self.lbl_progress.config(text=f"Scanning {fname} #{bi}... ({self._work_idx}/{total})")

        p = self._params
        board = load_board(fname, bi)

        if board:
            nc = board.total_cells()
            nl = len(board.layers)

            if p["c"][0] <= nc <= p["c"][1] and p["l"][0] <= nl <= p["l"][1]:
                engine = TEEngine()
                engine.color_count = p["cc"]
                engine.custom_triples = p.get("ct")

                # Retry loop
                for gen in range(p["retries"]):
                    board.clear_tiles()
                    engine.generate(board)
                    r = TileSolver.analyze(board, max_steps=p["sims"])

                    sr = r.get("solve_rate", 0)
                    dr = r.get("deadlock_rate", 100)
                    mn = r.get("min_moves") or 0
                    av = r.get("avg_moves") or 0
                    sc = r.get("complexity_score", 0)
                    lb = r.get("complexity_label", "?")

                    if not (p["s"][0] <= sr <= p["s"][1]):
                        continue
                    if not (p["d"][0] <= dr <= p["d"][1]):
                        continue
                    if not (p["mm"][0] <= mn <= p["mm"][1]):
                        continue
                    if not (p["am"][0] <= av <= p["am"][1]):
                        continue
                    if not (p["sc"][0] <= sc <= p["sc"][1]):
                        continue
                    if p["diff"] != "Any" and lb != p["diff"]:
                        continue

                    # New scoring with optional batch sampling
                    ns_w = {"X": self.w_X.get(), "Y": self.w_Y.get(),
                            "Z": self.w_Z.get(), "K": self.w_K.get()}
                    n_samples = p.get("samples", 1)

                    try:
                        if n_samples > 1:
                            # Batch: run N generates, collect min/max
                            batch_engine = TEEngine()
                            batch_engine.color_count = p["cc"]
                            if p.get("ct"):
                                batch_engine.custom_triples = p["ct"]
                            ig_vals, ng_vals, cv_vals, fs_vals = [], [], [], []
                            for _ in range(n_samples):
                                batch_engine.generate(board)
                                s = DifficultyScorer.compute_full_score(board, weights=ns_w)
                                ig_vals.append(s.get("inter_group", 0))
                                ng_vals.append(s.get("intra_group", 0))
                                cv_vals.append(s.get("cover100", 0))
                                fs_vals.append(s.get("final_score", 0))
                            # Restore last generate for display
                            batch_engine.generate(board)
                            ns = DifficultyScorer.compute_full_score(board, weights=ns_w)
                            ig_min, ig_max = round(min(ig_vals), 1), round(max(ig_vals), 1)
                            ng_min, ng_max = round(min(ng_vals), 1), round(max(ng_vals), 1)
                        else:
                            ns = DifficultyScorer.compute_full_score(board, weights=ns_w)
                            ig_min = ig_max = ns.get("inter_group", 0)
                            ng_min = ng_max = ns.get("intra_group", 0)
                    except Exception:
                        ns = {}
                        ig_min = ig_max = ng_min = ng_max = 0

                    n_final = ns.get("final_score", 0)

                    # Filters: final score
                    ns_lo, ns_hi = p.get("ns", (0, 9999))
                    if not (ns_lo <= n_final <= ns_hi):
                        continue
                    # Filters: inter-group range
                    ig_lo, ig_hi = p.get("ig", (0, 9999))
                    if not (ig_lo <= ig_min and ig_max <= ig_hi):
                        continue
                    # Filters: intra-group range
                    ng_lo, ng_hi = p.get("ng", (0, 9999))
                    if not (ng_lo <= ng_min and ng_max <= ng_hi):
                        continue

                    # Match!
                    best = {
                        "file": fname, "board": bi, "cells": nc, "layers": nl,
                        "gen": gen + 1, "solve": sr, "dead": dr,
                        "minmv": mn, "avgmv": av, "score": sc, "label": lb,
                        "n_layout": ns.get("layout", 0),
                        "n_inter": ns.get("inter_group", 0),
                        "n_intra": ns.get("intra_group", 0),
                        "n_cover": ns.get("cover100", 0),
                        "n_final": n_final,
                        "ig_min": ig_min, "ig_max": ig_max,
                        "ng_min": ng_min, "ng_max": ng_max,
                    }
                    self.results.append(best)
                    self.tree.insert("", "end", values=(
                        fname, bi, nc, nl, gen + 1,
                        f"{sr:.0f}", f"{dr:.0f}",
                        mn or "-", f"{av:.0f}" if av else "-",
                        sc, lb,
                        ns.get("layout", "-"), ns.get("inter_group", "-"),
                        ns.get("intra_group", "-"), ns.get("cover100", "-"),
                        n_final,
                        ig_min, ig_max, ng_min, ng_max,
                    ))
                    self._found += 1
                    break

        # Schedule next board — yield control to tkinter event loop
        self.after(1, self._process_next)

    def _sort(self, col):
        """Sort results by clicking column header."""
        rev = self._sort_reverse.get(col, False)
        items = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda t: float(t[0]) if t[0] not in ("-", "?") else -1, reverse=rev)
        except ValueError:
            items.sort(key=lambda t: t[0], reverse=rev)
        for i, (_, k) in enumerate(items):
            self.tree.move(k, "", i)
        self._sort_reverse[col] = not rev

    def _get_sel(self):
        sel = self.tree.selection()
        if not sel: return None, None
        v = self.tree.item(sel[0])["values"]
        return str(v[0]), int(v[1])

    def _on_select(self, event):
        f, b = self._get_sel()
        if f is None: return
        self.app.v_file.set(f)
        self.app._on_file_change()
        self.app.v_bidx.set(b)
        self.app._load_board()
        self.app._generate()

    def _play_selected(self):
        f, b = self._get_sel()
        if f is None: return
        board = load_board(f, b)
        if not board: return
        engine = TEEngine()
        engine.color_count = self._params.get("cc", 4) if hasattr(self, '_params') else 4
        engine.generate(board)
        PlayWindow(self, board)

    def _pin_selected(self):
        f, b = self._get_sel()
        if f is None: return
        # Find stats from results
        stats = {}
        for r in self.results:
            if r["file"] == f and r["board"] == b:
                stats = r
                break
        meta.add_pinned(f, b, stats=stats)
        self.lbl_progress.config(text=f"Pinned: {f} #{b}")

    def _pin_all(self):
        for r in self.results:
            meta.add_pinned(r["file"], r["board"], stats=r)
        self.lbl_progress.config(text=f"Pinned all {len(self.results)} results")

    def _export(self, mode):
        if not self.results and mode != "selected":
            self.lbl_progress.config(text="No results to export")
            return

        out_dir = filedialog.askdirectory(title="Choose Export Folder",
                                            initialdir=self.app.export_dir)
        if not out_dir:
            return
        self.app.export_dir = out_dir  # remember choice

        p = self._params
        tag = f"cc{p['cc']}_s{p['s'][0]}-{p['s'][1]}"

        if mode == "json":
            path = os.path.join(out_dir, f"search_{tag}.json")
            with open(path, "w") as f:
                json.dump({"params": {k: v for k, v in p.items()},
                            "count": len(self.results), "results": self.results}, f, indent=2)
            self.lbl_progress.config(text=f"Saved {len(self.results)} results to {path}")

        elif mode == "csv":
            path = os.path.join(out_dir, f"search_{tag}.csv")
            cols = ["file", "board", "cells", "layers", "gen", "solve", "dead",
                    "minmv", "avgmv", "score", "label"]
            with open(path, "w") as f:
                f.write(",".join(cols) + "\n")
                for r in self.results:
                    f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")
            self.lbl_progress.config(text=f"Saved CSV: {path}")

        elif mode == "boards_json":
            # Export each matching board as individual JSON with full tile data
            count = 0
            engine = TEEngine()
            engine.color_count = p["cc"]
            for r in self.results:
                board = load_board(r["file"], r["board"])
                if not board:
                    continue
                board.clear_tiles()
                engine.generate(board)
                data = {
                    "source": r,
                    "board": {
                        "name": board.name,
                        "layers": [{
                            "id": l.id,
                            "cells": [{"x": c.x, "y": c.y, "tile": c.tile_id}
                                       for c in l.cells]
                        } for l in board.layers]
                    }
                }
                fname = f"board_{r['file'].replace('.json','')}_{r['board']}.json"
                with open(os.path.join(out_dir, fname), "w") as f:
                    json.dump(data, f, indent=2)
                count += 1
            self.lbl_progress.config(text=f"Exported {count} board files to {out_dir}/")

        elif mode == "boards_single":
            # All matching boards in one JSON file
            all_boards = []
            engine = TEEngine()
            engine.color_count = p["cc"]
            for r in self.results:
                board = load_board(r["file"], r["board"])
                if not board:
                    continue
                board.clear_tiles()
                engine.generate(board)
                all_boards.append({
                    "source": r,
                    "layers": [{
                        "id": l.id,
                        "cells": [{"x": c.x, "y": c.y, "tile": c.tile_id}
                                   for c in l.cells]
                    } for l in board.layers]
                })
            path = os.path.join(out_dir, f"all_boards_{tag}.json")
            with open(path, "w") as f:
                json.dump({"count": len(all_boards), "boards": all_boards}, f, indent=2)
            self.lbl_progress.config(text=f"Saved {len(all_boards)} boards to {path}")

        elif mode == "selected":
            sel = self.tree.selection()
            if not sel:
                self.lbl_progress.config(text="No row selected")
                return
            v = self.tree.item(sel[0])["values"]
            fname, bidx = str(v[0]), int(v[1])
            board = load_board(fname, bidx)
            if not board:
                return
            engine = TEEngine()
            engine.color_count = p["cc"]
            engine.generate(board)
            data = {
                "source": {"file": fname, "board": bidx},
                "layers": [{
                    "id": l.id,
                    "cells": [{"x": c.x, "y": c.y, "tile": c.tile_id}
                               for c in l.cells]
                } for l in board.layers]
            }
            path = os.path.join(out_dir, f"board_{fname.replace('.json','')}_{bidx}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            self.lbl_progress.config(text=f"Saved to {path}")


# ─────────────────────────────────────────────────────────────
# Pinned List Window
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Project Manager Window
# ─────────────────────────────────────────────────────────────

class ProjectWindow(tk.Toplevel):
    """Create, switch, and manage isolated project workspaces."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Project Manager")
        self.geometry("600x480")
        self.configure(bg="#1A1A2E")
        self.transient(app)
        self._build()
        self._refresh()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg="#1E1E2E")
        hdr.pack(fill="x", padx=8, pady=8)
        tk.Label(hdr, text="Projects", bg="#1E1E2E", fg="#5DADE2",
                  font=("Segoe UI", 14, "bold")).pack(side="left", padx=8)

        active = meta.get_active_project()
        self.lbl_active = tk.Label(hdr, text=f"Active: {active['name'] if active else 'None'}",
                                     bg="#1E1E2E", fg="#58D68D", font=("Consolas", 10))
        self.lbl_active.pack(side="right", padx=8)

        # Project list
        self.tree = ttk.Treeview(self, columns=("name", "files", "created", "desc"),
                                   show="headings", height=10)
        self.tree.heading("name", text="Project")
        self.tree.heading("files", text="Files")
        self.tree.heading("created", text="Created")
        self.tree.heading("desc", text="Description")
        self.tree.column("name", width=140)
        self.tree.column("files", width=50)
        self.tree.column("created", width=130)
        self.tree.column("desc", width=200)
        self.tree.pack(fill="both", expand=True, padx=8, pady=4)

        # Buttons
        btn = tk.Frame(self, bg="#1A1A2E")
        btn.pack(fill="x", padx=8, pady=8)

        tk.Button(btn, text="New Project", bg="#1B5E20", fg="#FFF",
                   font=("Consolas", 10, "bold"), relief="flat", padx=12,
                   command=self._new).pack(side="left", padx=4)
        tk.Button(btn, text="Switch To", bg="#1565C0", fg="#FFF",
                   font=("Consolas", 10), relief="flat", padx=10,
                   command=self._switch).pack(side="left", padx=4)
        tk.Button(btn, text="Import Files...", bg="#2D2D44", fg="#CCD",
                   font=("Consolas", 9), relief="flat", padx=8,
                   command=self._import_files).pack(side="left", padx=4)
        tk.Button(btn, text="Import Folder...", bg="#2D2D44", fg="#CCD",
                   font=("Consolas", 9), relief="flat", padx=8,
                   command=self._import_dir).pack(side="left", padx=4)
        tk.Button(btn, text="Delete", bg="#B71C1C", fg="#FFF",
                   font=("Consolas", 9), relief="flat", padx=8,
                   command=self._delete).pack(side="right", padx=4)

        self.lbl_status = tk.Label(self, text="", bg="#1A1A2E", fg="#778",
                                     font=("Consolas", 9))
        self.lbl_status.pack(fill="x", padx=8, pady=(0, 4))

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for p in meta.list_projects():
            tag = "active" if p["active"] else ""
            name = ("* " if p["active"] else "") + p["name"]
            self.tree.insert("", "end", values=(
                name, p["n_files"], p["created"], p["description"]
            ), tags=(tag,))
        self.tree.tag_configure("active", foreground="#58D68D")
        active = meta.get_active_project()
        self.lbl_active.config(text=f"Active: {active['name'] if active else 'None'}")

    def _get_sel_folder(self):
        sel = self.tree.selection()
        if not sel: return None
        name = self.tree.item(sel[0])["values"][0]
        name = name.lstrip("* ")
        for p in meta.list_projects():
            if p["name"] == name:
                return p["folder"]
        return None

    def _new(self):
        dlg = tk.Toplevel(self)
        dlg.title("New Project")
        dlg.geometry("350x180")
        dlg.configure(bg="#1E1E2E")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Project Name:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 10)).pack(anchor="w", padx=16, pady=(16, 4))
        v_name = tk.StringVar()
        tk.Entry(dlg, textvariable=v_name, bg="#16161E", fg="#CCD",
                  font=("Consolas", 11), insertbackground="#CCD").pack(fill="x", padx=16)

        tk.Label(dlg, text="Description:", bg="#1E1E2E", fg="#AAB",
                  font=("Consolas", 10)).pack(anchor="w", padx=16, pady=(8, 4))
        v_desc = tk.StringVar()
        tk.Entry(dlg, textvariable=v_desc, bg="#16161E", fg="#CCD",
                  font=("Consolas", 10), insertbackground="#CCD").pack(fill="x", padx=16)

        def create():
            name = v_name.get().strip()
            if not name:
                return
            meta.create_project(name, v_desc.get().strip())
            dlg.destroy()
            self._refresh()
            self.lbl_status.config(text=f"Created project: {name}")

        tk.Button(dlg, text="Create", bg="#1B5E20", fg="#FFF",
                   font=("Consolas", 10, "bold"), relief="flat", padx=16,
                   command=create).pack(pady=12)

    def _switch(self):
        folder = self._get_sel_folder()
        if not folder: return
        meta.set_active_project(folder)
        proj = meta.get_active_project()
        if proj:
            # Switch main app's levels dir to project's levels dir
            set_levels_dir(proj["levels_dir"])
            self.app.export_dir = proj["exports_dir"]
            files = list_level_files()
            self.app.file_combo.config(values=files)
            self.app.lbl_folder.config(text=f"Project: {proj['name']}")
            if files:
                self.app.v_file.set(files[0])
                self.app._on_file_change()
                self.app._load_board()
            self.app.status.set(f"Switched to project: {proj['name']} ({len(files)} files)")
        self._refresh()

    def _import_files(self):
        folder = self._get_sel_folder()
        if not folder:
            self.lbl_status.config(text="Select a project first")
            return
        paths = filedialog.askopenfilenames(
            title="Import Level Files",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not paths: return
        n = meta.import_files_to_project(folder, paths)
        self.lbl_status.config(text=f"Imported {n} files")
        self._refresh()

    def _import_dir(self):
        folder = self._get_sel_folder()
        if not folder:
            self.lbl_status.config(text="Select a project first")
            return
        d = filedialog.askdirectory(title="Import All JSONs From Folder")
        if not d: return
        n = meta.import_folder_to_project(folder, d)
        self.lbl_status.config(text=f"Imported {n} files from {os.path.basename(d)}")
        self._refresh()

    def _delete(self):
        folder = self._get_sel_folder()
        if not folder: return
        if not messagebox.askyesno("Delete Project",
                                    f"Delete project '{folder}' and ALL its data?", parent=self):
            return
        meta.delete_project(folder)
        self._refresh()
        self.lbl_status.config(text=f"Deleted: {folder}")


class PinnedListWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Pinned Levels")
        self.geometry("650x450")
        self.configure(bg="#1A1A2E")
        self.transient(app)
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # Toolbar
        tb = tk.Frame(self, bg="#1E1E2E")
        tb.pack(fill="x", padx=4, pady=4)
        tk.Label(tb, text="Pinned Levels", bg="#1E1E2E", fg="#5DADE2",
                  font=("Segoe UI", 12, "bold")).pack(side="left", padx=8)
        tk.Button(tb, text="Refresh", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=self._refresh).pack(side="right", padx=4)
        tk.Button(tb, text="Remove Selected", bg="#B71C1C", fg="#FFF", font=("Consolas", 9),
                   relief="flat", command=self._remove).pack(side="right", padx=4)
        tk.Button(tb, text="Export All", bg="#1565C0", fg="#FFF", font=("Consolas", 9),
                   relief="flat", command=self._export_all).pack(side="right", padx=4)

        # Table
        cols = ("file", "board", "note", "solve", "complexity", "pinned")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=15)
        for col, txt, w in [("file", "File", 110), ("board", "#", 40), ("note", "Note", 150),
                              ("solve", "Solve%", 60), ("complexity", "Difficulty", 80),
                              ("pinned", "Pinned At", 130)]:
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w)
        self.tree.pack(fill="both", expand=True, padx=4, pady=4)

        # Buttons
        btn = tk.Frame(self, bg="#1A1A2E")
        btn.pack(fill="x", padx=4, pady=4)
        tk.Button(btn, text="Load in Main", bg="#2D2D44", fg="#CCD", font=("Consolas", 10),
                   relief="flat", padx=12, command=self._load).pack(side="left", padx=4)
        tk.Button(btn, text="PLAY", bg="#1B5E20", fg="#FFF", font=("Consolas", 10, "bold"),
                   relief="flat", padx=16, command=self._play).pack(side="left", padx=4)

        tk.Label(btn, text="Double-click to load | Select + Play to test",
                  bg="#1A1A2E", fg="#445", font=("Consolas", 8)).pack(side="right", padx=8)
        self.tree.bind("<Double-1>", lambda e: self._load())

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for p in meta.get_pinned():
            sr = (p.get("stats") or {}).get("solve_rate", "")
            cl = (p.get("stats") or {}).get("complexity_label", "")
            self.tree.insert("", "end", values=(
                p["file"], p["board"], p.get("note", ""),
                f"{sr:.0f}" if isinstance(sr, (int, float)) else sr,
                cl, p.get("pinned_at", ""),
            ))

    def _get_selected(self):
        sel = self.tree.selection()
        if not sel: return None, None
        v = self.tree.item(sel[0])["values"]
        return str(v[0]), int(v[1])

    def _load(self):
        f, b = self._get_selected()
        if f is None: return
        self.app.v_file.set(f)
        self.app._on_file_change()
        self.app.v_bidx.set(b)
        self.app._load_board()
        self.app._generate()

    def _play(self):
        f, b = self._get_selected()
        if f is None: return
        board = load_board(f, b)
        if not board: return
        engine = TEEngine()
        engine.color_count = self.app.engine.color_count
        engine.generate(board)
        PlayWindow(self, board)

    def _remove(self):
        f, b = self._get_selected()
        if f is None: return
        meta.remove_pinned(f, b)
        self._refresh()

    def _export_all(self):
        d = filedialog.askdirectory(title="Export Pinned Levels",
                                      initialdir=self.app.export_dir)
        if not d: return
        self.app.export_dir = d
        engine = TEEngine()
        engine.color_count = self.app.engine.color_count
        count = 0
        for p in meta.get_pinned():
            board = load_board(p["file"], p["board"])
            if not board: continue
            engine.generate(board)
            r = TileSolver.analyze(board, max_steps=100)
            meta.export_with_metadata(board, d, engine, r, tags=set(p.get("tags", [])))
            count += 1
        meta.build_collection_index(d)
        messagebox.showinfo("Export Done", f"Exported {count} pinned boards to {d}\n"
                            f"Index: _index.json", parent=self)


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget; self.text = text; self.tw = None
        widget.bind("<Enter>", self.show); widget.bind("<Leave>", self.hide)
    def show(self, e):
        self.tw = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{e.x_root+12}+{e.y_root+8}")
        tk.Label(tw, text=self.text, bg="#333", fg="#EEE", font=("Consolas", 9),
                 padx=6, pady=3, wraplength=300, justify="left").pack()
    def hide(self, e):
        if self.tw: self.tw.destroy(); self.tw = None


# ─────────────────────────────────────────────────────────────
# Application
# ─────────────────────────────────────────────────────────────

class SplashScreen(tk.Toplevel):
    """Splash screen shown on startup."""
    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)

        # Center on screen
        sw, sh = 480, 320
        x = (self.winfo_screenwidth() - sw) // 2
        y = (self.winfo_screenheight() - sh) // 2
        self.geometry(f"{sw}x{sh}+{x}+{y}")
        self.configure(bg="#0D0D1A")
        self.attributes("-topmost", True)

        # Border glow effect
        border = tk.Frame(self, bg="#1565C0", padx=2, pady=2)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg="#0D0D1A")
        inner.pack(fill="both", expand=True)

        # Content
        tk.Label(inner, text="TILE LEVEL SIMULATOR",
                  bg="#0D0D1A", fg="#5DADE2",
                  font=("Segoe UI", 20, "bold")).pack(pady=(35, 5))

        tk.Label(inner, text="v3.2 — AI-Powered",
                  bg="#0D0D1A", fg="#445566",
                  font=("Segoe UI", 12)).pack()

        # Decorative line
        tk.Frame(inner, bg="#1565C0", height=2).pack(fill="x", padx=60, pady=18)

        tk.Label(inner, text="Created by",
                  bg="#0D0D1A", fg="#556677",
                  font=("Segoe UI", 10)).pack()

        tk.Label(inner, text="Hai Tran Ngoc",
                  bg="#0D0D1A", fg="#FFFFFF",
                  font=("Segoe UI", 18, "bold")).pack(pady=(4, 6))

        tk.Label(inner, text="Telegram  @OrangeTran",
                  bg="#0D0D1A", fg="#5DADE2",
                  font=("Segoe UI", 11)).pack(pady=(2, 0))

        # Bottom tagline
        tk.Label(inner, text="Triple-Match Level Design & Analysis Tool",
                  bg="#0D0D1A", fg="#334455",
                  font=("Consolas", 9)).pack(side="bottom", pady=12)

        # Loading bar animation
        self.bar = tk.Canvas(inner, bg="#0D0D1A", height=4, highlightthickness=0)
        self.bar.pack(fill="x", padx=60, side="bottom", pady=(0, 8))
        self._bar_pos = 0
        self._animate_bar()

    def _animate_bar(self):
        self.bar.delete("all")
        w = self.bar.winfo_width() or 360
        bw = 80
        x = self._bar_pos % (w + bw) - bw
        self.bar.create_rectangle(x, 0, x + bw, 4, fill="#1565C0", outline="")
        self._bar_pos += 4
        if self.winfo_exists():
            self.after(20, self._animate_bar)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()  # hide main window during splash
        self.title("Tile Explorer Level Simulator")
        self.geometry("1400x850")
        self.configure(bg="#1E1E2E")
        self.engine = TEEngine()
        self.board = None
        self.history = []  # for comparison
        self.export_dir = r"D:\_Rac\tile_explore\exports"  # default export directory
        self._imported_file = None  # for single-file import mode

        # Show splash screen
        self.splash = SplashScreen(self)
        self.after(2500, self._close_splash)

    def _close_splash(self):
        if self.splash and self.splash.winfo_exists():
            self.splash.destroy()
        self.splash = None
        self.deiconify()  # show main window
        self._build()
        self.after(200, self._load_default)

    def _build(self):
        s = ttk.Style(); s.theme_use("clam")
        for n, bg, fg, ft in [
            ("D.TFrame", "#1E1E2E", None, None),
            ("D.TLabel", "#1E1E2E", "#AAB", ("Segoe UI", 9)),
            ("H.TLabel", "#1E1E2E", "#FFF", ("Segoe UI", 10, "bold")),
            ("S.TLabel", "#1E1E2E", "#778", ("Segoe UI", 8)),
            ("D.TButton", "#2D2D44", "#CCD", ("Segoe UI", 9)),
            ("Go.TButton", "#1B5E20", "#FFF", ("Segoe UI", 11, "bold")),
            ("Warn.TButton", "#B71C1C", "#FFF", ("Segoe UI", 9)),
        ]:
            kw = {"background": bg}
            if fg: kw["foreground"] = fg
            if ft: kw["font"] = ft
            s.configure(n, **kw)
        s.configure("D.TCheckbutton", background="#1E1E2E", foreground="#AAB", font=("Segoe UI", 9))
        s.configure("D.TRadiobutton", background="#1E1E2E", foreground="#AAB", font=("Segoe UI", 9))
        s.configure("D.TLabelframe", background="#1E1E2E", foreground="#CCD", font=("Segoe UI", 9))
        s.configure("D.TLabelframe.Label", background="#1E1E2E", foreground="#8899AA", font=("Segoe UI", 9, "bold"))
        s.map("D.TButton", background=[("active","#3D3D55")])
        s.map("Go.TButton", background=[("active","#2E7D32")])

        # ─── Menu Bar ───
        self._build_menubar()

        top = ttk.Frame(self, style="D.TFrame")
        top.pack(fill="both", expand=True)

        # ─── LEFT PANEL (scrollable) ───
        left_outer = ttk.Frame(top, style="D.TFrame", width=310)
        left_outer.pack(side="left", fill="y", padx=(4,0), pady=4)
        left_outer.pack_propagate(False)

        lcanvas = tk.Canvas(left_outer, bg="#1E1E2E", highlightthickness=0, width=290)
        lscroll = ttk.Scrollbar(left_outer, orient="vertical", command=lcanvas.yview)
        self.left = ttk.Frame(lcanvas, style="D.TFrame")
        self.left.bind("<Configure>", lambda e: lcanvas.configure(scrollregion=lcanvas.bbox("all")))
        lcanvas.create_window((0,0), window=self.left, anchor="nw")
        lcanvas.configure(yscrollcommand=lscroll.set)
        lcanvas.pack(side="left", fill="both", expand=True)
        lscroll.pack(side="right", fill="y")
        # Mouse wheel on left panel
        def _on_left_scroll(e):
            lcanvas.yview_scroll(-1 * (e.delta // 120), "units")
        # Only scroll left panel when mouse is actually over it
        def _on_left_scroll(e):
            # Check if mouse is over the left panel canvas
            try:
                widget = e.widget
                if widget is lcanvas or widget.master is self.left or str(widget).startswith(str(lcanvas)):
                    lcanvas.yview_scroll(-1 * (e.delta // 120), "units")
            except (AttributeError, tk.TclError):
                pass
        lcanvas.bind_all("<MouseWheel>", _on_left_scroll, add="+")

        self._build_board_section()
        self._build_preset_section()
        self._build_params_section()
        self._build_action_section()

        # ─── CENTER: Canvas ───
        center = ttk.Frame(top, style="D.TFrame")
        center.pack(side="left", fill="both", expand=True, padx=2, pady=4)
        self._build_view_toolbar(center)
        self.canvas = SimCanvas(center)
        self.canvas.pack(fill="both", expand=True)

        # ─── RIGHT: Stats ───
        right = ttk.Frame(top, style="D.TFrame", width=240)
        right.pack(side="right", fill="y", padx=(0,4), pady=4)
        right.pack_propagate(False)
        self._build_stats_panel(right)

        # Status
        self.status = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status, bg="#16161E", fg="#667",
                 font=("Consolas", 9), anchor="w", padx=8).pack(fill="x", side="bottom")

    # ── Board Section ──
    # ── Menu Bar ──
    def _build_menubar(self):
        mb = tk.Menu(self, bg="#1E1E2E", fg="#CCD", activebackground="#3D3D55",
                      activeforeground="#FFF", font=("Segoe UI", 9))

        # File
        file_m = tk.Menu(mb, tearoff=0)
        file_m.add_command(label="Load Board...", command=self._load_board, accelerator="Ctrl+L")
        file_m.add_command(label="Random Board", command=self._random_board, accelerator="Ctrl+R")
        file_m.add_separator()
        file_m.add_command(label="Import File...", command=self._import_file, accelerator="Ctrl+I")
        file_m.add_command(label="Import Folder...", command=self._import_folder)
        file_m.add_separator()
        file_m.add_command(label="Export JSON", command=self._export)
        file_m.add_command(label="Export Stones Format", command=self._export_stones)
        file_m.add_command(label="Save Snapshot", command=self._snapshot)
        file_m.add_separator()
        file_m.add_command(label="Exit", command=self.quit, accelerator="Alt+F4")
        mb.add_cascade(label="File", menu=file_m)

        # Generate
        gen_m = tk.Menu(mb, tearoff=0)
        gen_m.add_command(label="Generate Tiles", command=self._generate, accelerator="Enter")
        gen_m.add_command(label="Clear Tiles", command=self._clear)
        gen_m.add_separator()
        gen_m.add_command(label="Analyze Solvability", command=self._analyze, accelerator="Ctrl+A")
        mb.add_cascade(label="Generate", menu=gen_m)

        # Edit
        edit_m = tk.Menu(mb, tearoff=0)
        edit_m.add_command(label="Edit All Layers", command=lambda: self._open_editor("all"))
        edit_m.add_command(label="Edit Active Layer", command=lambda: self._open_editor("active"))
        edit_m.add_command(label="Edit Select Layers...", command=lambda: self._open_editor("pick"))
        mb.add_cascade(label="Edit", menu=edit_m)

        # View
        view_m = tk.Menu(mb, tearoff=0)
        view_m.add_command(label="Toggle 3D View", command=lambda: (self.v_3d.set(not self.v_3d.get()), self._toggle_3d()))
        view_m.add_command(label="Zoom to Fit", command=lambda: self.canvas.fit(self.board) if self.board else None)
        view_m.add_separator()
        view_m.add_command(label="Show All Layers", command=lambda: (self.v_show.set("all"), self._repaint()))
        view_m.add_command(label="Show Active Only", command=lambda: (self.v_show.set("active"), self._repaint()))
        mb.add_cascade(label="View", menu=view_m)

        # Play
        play_m = tk.Menu(mb, tearoff=0)
        play_m.add_command(label="Play Level", command=self._open_play, accelerator="F5")
        mb.add_cascade(label="Play", menu=play_m)

        # Presets
        preset_m = tk.Menu(mb, tearoff=0)
        for name in DIFFICULTY_PRESETS:
            preset_m.add_command(label=name, command=lambda n=name: self._apply_preset(n))
        mb.add_cascade(label="Presets", menu=preset_m)

        # Search
        # Project
        proj_m = tk.Menu(mb, tearoff=0)
        proj_m.add_command(label="Project Manager...", command=self._open_projects, accelerator="Ctrl+P")
        mb.add_cascade(label="Project", menu=proj_m)

        # Search
        search_m = tk.Menu(mb, tearoff=0)
        search_m.add_command(label="Find Levels...", command=self._open_finder, accelerator="Ctrl+F")
        mb.add_cascade(label="Search", menu=search_m)

        # MCP / AI
        mcp_m = tk.Menu(mb, tearoff=0)
        mcp_m.add_command(label="Start MCP Server", command=self._start_mcp_server)
        mcp_m.add_command(label="Stop MCP Server", command=self._stop_mcp_server)
        mcp_m.add_separator()
        mcp_m.add_command(label="Connection Guide", command=self._show_mcp_guide)
        mcp_m.add_command(label="View Event Logs", command=self._show_mcp_logs)
        mb.add_cascade(label="MCP / AI", menu=mcp_m)

        # Help
        help_m = tk.Menu(mb, tearoff=0)
        help_m.add_command(label="User Guide", command=self._show_guide)
        help_m.add_command(label="CLI Commands", command=self._show_cli_help)
        help_m.add_separator()
        help_m.add_command(label="About", command=self._show_about)
        mb.add_cascade(label="Help", menu=help_m)

        self.config(menu=mb)

        # Keyboard shortcuts
        self.bind("<Control-l>", lambda e: self._load_board())
        self.bind("<Control-r>", lambda e: self._random_board())
        self.bind("<Control-a>", lambda e: self._full_report())
        self.bind("<F5>", lambda e: self._open_play())
        self.bind("<Control-f>", lambda e: self._open_finder())
        self.bind("<Control-i>", lambda e: self._import_file())
        self.bind("<Control-p>", lambda e: self._open_projects())

    # ── Level Finder ──
    def _open_projects(self):
        ProjectWindow(self)

    def _open_finder(self):
        FinderWindow(self)

    def _show_about(self):
        dlg = tk.Toplevel(self)
        dlg.title("About")
        dlg.geometry("380x280")
        dlg.configure(bg="#1A1A2E")
        dlg.transient(self)
        dlg.resizable(False, False)

        tk.Label(dlg, text="Tile Explorer Level Simulator",
                  bg="#1A1A2E", fg="#5DADE2", font=("Segoe UI", 16, "bold")).pack(pady=(24, 4))
        tk.Label(dlg, text="v3.2 — AI-Powered", bg="#1A1A2E", fg="#778",
                  font=("Segoe UI", 11)).pack()

        tk.Frame(dlg, bg="#333", height=1).pack(fill="x", padx=40, pady=12)

        tk.Label(dlg, text="Created by", bg="#1A1A2E", fg="#889",
                  font=("Segoe UI", 10)).pack()
        tk.Label(dlg, text="Tran Ngoc Hai", bg="#1A1A2E", fg="#FFF",
                  font=("Segoe UI", 14, "bold")).pack(pady=(2, 8))

        tk.Label(dlg, text="Contact: Telegram @OrangeTran",
                  bg="#1A1A2E", fg="#5DADE2", font=("Segoe UI", 10)).pack()
        tk.Label(dlg, text="MCP Server: 27 tools for AI integration",
                  bg="#1A1A2E", fg="#50C878", font=("Segoe UI", 9)).pack(pady=(4, 16))

        tk.Button(dlg, text="OK", bg="#2D2D44", fg="#CCD", font=("Segoe UI", 10),
                   relief="flat", padx=24, command=dlg.destroy).pack(pady=4)

    # ── MCP / AI ──
    _mcp_process = None

    def _start_mcp_server(self):
        """Show instructions to start MCP server manually."""
        import sys
        script = None
        for d in [os.path.dirname(sys.executable),
                  os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
            p = os.path.join(d, "tile_mcp_server.py")
            if os.path.exists(p):
                script = p
                break

        if script:
            msg = (f"MCP Server script found at:\n{script}\n\n"
                   f"To start, open a terminal and run:\n"
                   f"  python \"{script}\"\n\n"
                   f"Or configure Claude Code .mcp.json to auto-start.\n"
                   f"See MCP / AI > Connection Guide for details.")
        else:
            msg = ("tile_mcp_server.py not found.\n\n"
                   "Place it next to the app and run:\n"
                   "  python tile_mcp_server.py")

        messagebox.showinfo("Start MCP Server", msg)
        self.status.set("See MCP Connection Guide for setup instructions")
        logger.log_event("mcp_guide_shown")

    def _stop_mcp_server(self):
        self.status.set("MCP server runs externally — close its terminal to stop")
        messagebox.showinfo("Stop MCP", "MCP server runs as a separate process.\n\n"
                           "Close its terminal window to stop it.")

    def _show_mcp_guide(self):
        dlg = tk.Toplevel(self)
        dlg.title("MCP / AI Connection Guide")
        dlg.geometry("700x620")
        dlg.configure(bg="#1A1A2E")
        dlg.transient(self)

        txt = tk.Text(dlg, bg="#16161E", fg="#CCD", font=("Consolas", 10),
                       wrap="word", borderwidth=0, padx=16, pady=16)
        txt.pack(fill="both", expand=True, padx=4, pady=4)

        # Find script path: beside exe, beside source, or cwd
        import sys
        for _d in [os.path.dirname(sys.executable),
                   os.path.dirname(os.path.abspath(__file__)), os.getcwd()]:
            _p = os.path.join(_d, "tile_mcp_server.py")
            if os.path.exists(_p):
                script_path = _p
                break
        else:
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tile_mcp_server.py")

        guide = f"""MCP SERVER — AI CONNECTION GUIDE
===================================

Tile Level Simulator v3.2 includes an MCP server with 27 tools
for AI agents (Claude, etc.) to control the tool programmatically.

WHAT CAN AI DO?
  - Load/create/edit board layouts
  - Generate tiles with any params
  - Score difficulty (single, batch, bulk 1000+ levels)
  - Plot difficulty curves across level progression
  - Search levels by criteria
  - Export in stones/stacks format
  - Manage pinned levels and projects
  - Read event logs for debugging

SETUP FOR CLAUDE CODE
=====================

Step 1: Ensure these files exist in your project folder:
  tile_mcp_server.py
  tile_api.py
  tile_logger.py
  tile_level_simulator.py
  tile_metadata.py

Step 2: Install MCP SDK:
  pip install mcp

Step 3: .mcp.json is already included in the project folder.
  If missing, create .mcp.json in your project root:

  {{
    "mcpServers": {{
      "tile-sim": {{
        "command": "python",
        "args": ["./tile_mcp_server.py"]
      }}
    }}
  }}

Step 4: Open Claude Code in this project folder:
  cd <your_project_folder>
  claude

Step 5: Claude Code will detect .mcp.json and ask to approve.
  Type /mcp to manage servers, or approve when prompted.

Step 6: Done! AI now has access to 27 tools.

ALTERNATIVE: GLOBAL CONFIG (any project, use absolute path)
============================================================

Add to ~/.claude/settings.json:

  {{
    "mcpServers": {{
      "tile-sim": {{
        "command": "python",
        "args": ["{script_path.replace(chr(92), '/')}"]
      }}
    }}
  }}

AVAILABLE TOOLS (27)
====================

Board Management:
  list_level_files    — list JSON files
  load_board          — load by file + index
  load_board_from_path — load from absolute path
  get_board_count     — count boards in file
  create_board        — create from layers spec
  edit_board          — add/remove/move/copy layers, cells
  get_board_info      — summary stats

Level Generation:
  generate_tiles      — generate with params
  list_presets        — show difficulty presets
  apply_preset        — get preset params

Difficulty Analysis:
  score_level         — new difficulty score
  batch_score         — N runs min/max/avg
  bulk_score_levels   — score 1000+ levels
  difficulty_curve    — data for plotting
  analyze_solvability — Monte Carlo solver

Search:
  search_levels       — find by criteria

Export:
  export_stones       — stones/stacks format
  export_with_metadata — full metadata export

Pin & Project:
  list_pinned / pin_level / unpin_level
  list_projects / create_project / switch_project

Config:
  get_weights / set_weights — scoring weights X,Y,Z,K
  get_recent_logs    — event log for debugging

EXAMPLE AI WORKFLOW
===================

1. load_board("level5.json", 3)
2. generate_tiles(board, {{"color_count": 4}})
3. score_level(board)  →  layout=2.1, final=12.5
4. batch_score(board, params, n_runs=50)  →  min/max
5. export_stones(board, "output.json")

For bulk analysis:
  difficulty_curve(params={{"color_count":4}})
  → returns scores for ALL levels, ready to plot
"""
        txt.insert("1.0", guide)
        txt.config(state="disabled")

        # Copy .mcp.json button
        def _copy_mcp_json():
            mcp_config = json.dumps({
                "mcpServers": {
                    "tile-sim": {
                        "command": "python",
                        "args": ["./tile_mcp_server.py"]
                    }
                }
            }, indent=2)
            self.clipboard_clear()
            self.clipboard_append(mcp_config)
            self.status.set("Copied .mcp.json to clipboard!")

        btn_frame = tk.Frame(dlg, bg="#1A1A2E")
        btn_frame.pack(fill="x", padx=8, pady=6)
        tk.Button(btn_frame, text="Copy .mcp.json to Clipboard",
                   bg="#1B5E20", fg="#FFF", font=("Consolas", 10, "bold"),
                   relief="flat", padx=16, command=_copy_mcp_json).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Close", bg="#2D2D44", fg="#CCD",
                   font=("Consolas", 10), relief="flat", padx=16,
                   command=dlg.destroy).pack(side="right", padx=4)

    def _show_mcp_logs(self):
        dlg = tk.Toplevel(self)
        dlg.title("MCP Event Logs")
        dlg.geometry("700x450")
        dlg.configure(bg="#1A1A2E")
        dlg.transient(self)

        txt = tk.Text(dlg, bg="#16161E", fg="#CCD", font=("Consolas", 9),
                       wrap="word", borderwidth=0, padx=12, pady=12)
        txt.pack(fill="both", expand=True, padx=4, pady=4)

        logs = logger.get_recent_logs(100)
        if not logs:
            txt.insert("1.0", "No events logged yet.\n\nEvents are logged when you:\n"
                       "- Generate tiles\n- Analyze solvability\n- Load boards\n"
                       "- Export files\n- Use MCP tools\n")
        else:
            for entry in reversed(logs):
                ts = entry.get("ts", "?")
                ev = entry.get("event", "?")
                # Format nicely
                details = {k: v for k, v in entry.items() if k not in ("ts", "event")}
                detail_str = "  ".join(f"{k}={v}" for k, v in details.items()) if details else ""
                tag = "error" if ev == "error" else ""
                txt.insert("end", f"[{ts}] {ev:16s} {detail_str}\n", tag)
            txt.tag_configure("error", foreground="#FF6B6B")
        txt.config(state="disabled")

        btn_frame = tk.Frame(dlg, bg="#1A1A2E")
        btn_frame.pack(fill="x", padx=8, pady=4)
        tk.Button(btn_frame, text="Refresh", bg="#2D2D44", fg="#CCD",
                   font=("Consolas", 9), relief="flat", padx=12,
                   command=lambda: (dlg.destroy(), self._show_mcp_logs())).pack(side="left", padx=4)
        tk.Button(btn_frame, text="Close", bg="#2D2D44", fg="#CCD",
                   font=("Consolas", 9), relief="flat", padx=12,
                   command=dlg.destroy).pack(side="right", padx=4)

    def _show_guide(self):
        dlg = tk.Toplevel(self)
        dlg.title("User Guide")
        dlg.geometry("600x550")
        dlg.configure(bg="#1A1A2E")
        dlg.transient(self)

        txt = tk.Text(dlg, bg="#16161E", fg="#CCD", font=("Consolas", 10),
                       wrap="word", borderwidth=0, padx=12, pady=12)
        txt.pack(fill="both", expand=True, padx=4, pady=4)

        guide = """TILE EXPLORER LEVEL SIMULATOR - USER GUIDE
==========================================

1. LOAD A BOARD
   - Select a level file (level1.json - level72.json)
   - Choose board index (0-99)
   - Click "Load" or use Prev/Next/Random
   - Click layers in the layer list to switch active layer

2. SET PARAMETERS
   - Color Count (2-9): number of tile types
   - Hard Code (0-3): difficulty tier
   - 5 Difficulty Knobs: toggle on/off
   - TileStyleMode: Standard / Enhanced / Extended
   - Binding: Random (shuffled) or Preset (deterministic)

3. GENERATE TILES
   - Press GENERATE or hit Enter
   - View tile distribution in Results panel
   - Check "All x3" (each type in multiples of 3)
   - History panel shows previous generations

4. ANALYZE SOLVABILITY
   - Runs 500 simulated playouts
   - Shows: solve rate, deadlock rate, complexity score
   - Per-layer clear analysis (avg moves to clear each layer)

5. VIEW MODES
   - 2D flat (default) or 3D isometric (checkbox)
   - All / Up to / Active layer filters
   - Pan: right-click drag | Zoom: scroll wheel

6. EDIT BOARD
   - Edit All: edit all layers
   - Edit Layer: edit only active layer
   - Edit Pick: choose which layers to edit
   - Tools: Add (A) / Erase (E) / Paint (P)
   - Import layers from another level while editing
   - Save applies changes + auto-regenerates

7. PLAY MODE
   - Click PLAY (green button) or press F5
   - Click uncovered tiles to pick them
   - Tiles go to 7-slot tray, grouped by type
   - 3 matching tiles auto-clear
   - Buffs: Shuffle (3x), Undo (3x), +1 Slot (1x)

KEYBOARD SHORTCUTS
   Enter     Generate tiles
   F5        Play level
   Ctrl+L    Load board
   Ctrl+R    Random board
   Ctrl+A    Full report (difficulty + solvability)
   A/E/P     Tools (in edit mode)
   1-9       Select color (in edit mode)
"""
        txt.insert("1.0", guide)
        txt.config(state="disabled")

    def _show_cli_help(self):
        dlg = tk.Toplevel(self)
        dlg.title("CLI Commands")
        dlg.geometry("650x550")
        dlg.configure(bg="#1A1A2E")
        dlg.transient(self)

        txt = tk.Text(dlg, bg="#16161E", fg="#CCD", font=("Consolas", 10),
                       wrap="word", borderwidth=0, padx=12, pady=12)
        txt.pack(fill="both", expand=True, padx=4, pady=4)

        # CLI reference from tile_metadata module
        txt.insert("1.0", meta.CLI_HELP)
        txt.config(state="disabled")

    # ── Board Section ──
    def _build_board_section(self):
        f = ttk.LabelFrame(self.left, text="Board Layout", style="D.TLabelframe", padding=6)
        f.pack(fill="x", padx=6, pady=(6,3))

        row = ttk.Frame(f, style="D.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="File:", style="D.TLabel", width=7).pack(side="left")
        self.v_file = tk.StringVar(value="level1.json")
        files = list_level_files()
        self.file_combo = ttk.Combobox(row, textvariable=self.v_file, values=files, width=16, font=("Consolas", 9))
        self.file_combo.pack(side="left", padx=2)
        self.file_combo.bind("<<ComboboxSelected>>", self._on_file_change)

        row2 = ttk.Frame(f, style="D.TFrame")
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Board:", style="D.TLabel", width=7).pack(side="left")
        self.v_bidx = tk.IntVar(value=0)
        self.sp_board = tk.Spinbox(row2, from_=0, to=99, textvariable=self.v_bidx,
                                    width=5, bg="#16161E", fg="#AAB", font=("Consolas", 9))
        self.sp_board.pack(side="left", padx=2)
        self.lbl_bcount = ttk.Label(row2, text="/ ?", style="S.TLabel")
        self.lbl_bcount.pack(side="left")

        row3 = ttk.Frame(f, style="D.TFrame")
        row3.pack(fill="x", pady=4)
        ttk.Button(row3, text="Load", style="D.TButton",
                    command=self._load_board).pack(side="left", padx=2, fill="x", expand=True)
        ttk.Button(row3, text="Prev", style="D.TButton", width=5,
                    command=lambda: self._nav_board(-1)).pack(side="left", padx=1)
        ttk.Button(row3, text="Next", style="D.TButton", width=5,
                    command=lambda: self._nav_board(1)).pack(side="left", padx=1)
        ttk.Button(row3, text="Random", style="D.TButton", width=7,
                    command=self._random_board).pack(side="left", padx=1)

        # Import buttons
        row4 = ttk.Frame(f, style="D.TFrame")
        row4.pack(fill="x", pady=2)
        ttk.Button(row4, text="Import File...", style="D.TButton",
                    command=self._import_file).pack(side="left", padx=2, fill="x", expand=True)
        ttk.Button(row4, text="Import Folder...", style="D.TButton",
                    command=self._import_folder).pack(side="left", padx=2, fill="x", expand=True)

        # Current folder label
        self.lbl_folder = ttk.Label(f, text=f"Folder: {os.path.basename(_levels_dir)}",
                                      style="S.TLabel")
        self.lbl_folder.pack(anchor="w")

        self.lbl_board_info = ttk.Label(f, text="No board loaded", style="S.TLabel")
        self.lbl_board_info.pack(anchor="w")

        # Visual layer list (like editor's layer panel)
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=4)
        ttk.Label(f, text="Layers", style="D.TLabel").pack(anchor="w")
        self.main_layer_frame = tk.Frame(f, bg="#1E1E2E")
        self.main_layer_frame.pack(fill="x")

    # ── Preset Section ──
    def _build_preset_section(self):
        f = ttk.LabelFrame(self.left, text="Quick Presets", style="D.TLabelframe", padding=6)
        f.pack(fill="x", padx=6, pady=3)

        row = None
        for i, (name, _) in enumerate(DIFFICULTY_PRESETS.items()):
            if i % 2 == 0:
                row = ttk.Frame(f, style="D.TFrame")
                row.pack(fill="x", pady=1)
            short = name.split("(")[0].strip() if "(" in name else name
            btn = ttk.Button(row, text=short, style="D.TButton",
                              command=lambda n=name: self._apply_preset(n))
            btn.pack(side="left", padx=1, fill="x", expand=True)
            Tooltip(btn, f"Apply preset: {name}")

    # ── Parameters Section ──
    def _build_params_section(self):
        # Core params
        f1 = ttk.LabelFrame(self.left, text="Tile Generation", style="D.TLabelframe", padding=6)
        f1.pack(fill="x", padx=6, pady=3)

        self.param_widgets = {}

        def slider_row(parent, label, var_name, lo, hi, tip="", is_float=False):
            row = ttk.Frame(parent, style="D.TFrame")
            row.pack(fill="x", pady=2)
            lbl = ttk.Label(row, text=f"{label}:", style="D.TLabel", width=13)
            lbl.pack(side="left")
            if tip: Tooltip(lbl, tip)

            var = tk.IntVar(value=getattr(self.engine, var_name))
            sc = tk.Scale(row, from_=lo, to=hi, orient="horizontal", variable=var,
                           bg="#1E1E2E", fg="#AAB", troughcolor="#2A2A3E",
                           highlightthickness=0, sliderrelief="flat",
                           font=("Consolas", 8), length=120, sliderlength=14)
            sc.pack(side="left", fill="x", expand=True, padx=2)
            self.param_widgets[var_name] = var
            return var

        slider_row(f1, "Level Number", "level_number", 1, 2000,
                    "Game level number. Controls which knobs activate:\n"
                    "Level 51+: TileValueReplace\nLevel 101+: TileDistanceCode")
        slider_row(f1, "Color Count", "color_count", 2, 25,
                    "Number of tile types (2=very easy, 9=Unity max, 10-25=tool-only).\n"
                    "For cc > 9: cells must be >= cc*10 (see docs/ALGORITHM_PERFORMANCE.md)")
        slider_row(f1, "Hard Code", "hard_code", 0, 3,
                    "HardTag difficulty tier from config:\n"
                    "0=normal, 1=slightly hard, 2=hard (+1 color), 3=extreme (+2 colors)")
        slider_row(f1, "HardBg Tiles", "hard_bg_count", 0, 10,
                    "Number of background obstacle tiles pre-assigned\n"
                    "before main tile binding (from HardBgTileDescribe)")

        # Difficulty knobs
        f2 = ttk.LabelFrame(self.left, text="Difficulty Knobs", style="D.TLabelframe", padding=6)
        f2.pack(fill="x", padx=6, pady=3)

        def check_row(parent, label, var_name, tip=""):
            var = tk.BooleanVar(value=getattr(self.engine, var_name))
            cb = ttk.Checkbutton(parent, text=label, variable=var, style="D.TCheckbutton")
            cb.pack(anchor="w", pady=1)
            if tip: Tooltip(cb, tip)
            self.param_widgets[var_name] = var
            return var

        check_row(f2, "1. LessTypeUpDownSide", "less_type",
                   "Reduce tile variety at top/bottom edges of each layer.\n"
                   "Edge cells use max(2, colorCount-2) types.\n"
                   "IDA: SetLessTypeUpDownSide → field 312")
        check_row(f2, "2. UpLayerEasy", "up_easy",
                   "Top layer uses fewer tile types (colorCount-1).\n"
                   "Makes the first visible tiles easier to match.\n"
                   "IDA: SetLevelUpLayerEasyData → field 359")
        check_row(f2, "4. TopTwoLayerEasy", "top2_easy",
                   "Top TWO layers use fewer types.\n"
                   "Combined with UpLayerEasy for progressive ease.\n"
                   "IDA: SetLevelTopTwoLayerEasyData → field 460")
        check_row(f2, "4b. TopThreeLayerEasy", "top3_easy",
                   "Top THREE layers use fewer types (extended — tool only).\n"
                   "See docs/ALGORITHM_PERFORMANCE.md for usage tips.")
        check_row(f2, "4c. TopFourLayerEasy", "top4_easy",
                   "Top FOUR layers use fewer types (extended — tool only).\n"
                   "Most aggressive easing — only useful with cc < 9.")

        slider_row(f2, "3. TileDistance", "distance", 0, 15,
                    "Min distance between same tile types (Knob 3).\n"
                    "Only active when Level > 100.\n"
                    "Value 9 = strict mode (from RemoteConfig).\n"
                    "IDA: SetTileDistanceCode → field 372")

        check_row(f2, "5. TileValueReplace", "val_replace",
                   "Swap tile types periodically to prevent pattern repetition.\n"
                   "Only active when Level >= 51.\n"
                   "Uses hash = level % 10 to determine swap.\n"
                   "IDA: SetTileValueReplaceData → field 612")

        slider_row(f2, "Replace Mode", "val_mode", 0, 3,
                    "TileValueReplace sub-mode (from RemoteConfig offset 872):\n"
                    "0=off, 1=mode A (3-field >= 1), 2=mode B, 3=same as 1")

        # Advanced
        f3 = ttk.LabelFrame(self.left, text="Advanced / RemoteConfig", style="D.TLabelframe", padding=6)
        f3.pack(fill="x", padx=6, pady=3)

        row = ttk.Frame(f3, style="D.TFrame")
        row.pack(fill="x", pady=2)
        lbl = ttk.Label(row, text="TileStyleMode:", style="D.TLabel", width=13)
        lbl.pack(side="left")
        Tooltip(lbl, "RemoteConfig offset 176:\n0=Standard (sets 73-76)\n"
                     "7=Enhanced (sets 77-81)\n3=Extended (sets 29-36, needs ExtendedTileMode)")
        self.v_style = tk.IntVar(value=0)
        for val, txt in [(0, "Std"), (7, "Enh"), (3, "Ext")]:
            ttk.Radiobutton(row, text=txt, variable=self.v_style, value=val,
                             style="D.TRadiobutton").pack(side="left", padx=3)

        self.v_ext = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(f3, text="ExtendedTileMode (2-9 colors)", variable=self.v_ext,
                              style="D.TCheckbutton")
        cb.pack(anchor="w", pady=1)
        Tooltip(cb, "RemoteConfig offset 504.\nEnables extended tile sets (29-36) with up to 9 colors.\n"
                    "Requires TileStyleMode=3 to take effect.")

        row2 = ttk.Frame(f3, style="D.TFrame")
        row2.pack(fill="x", pady=2)
        lbl2 = ttk.Label(row2, text="Binding:", style="D.TLabel", width=13)
        lbl2.pack(side="left")
        Tooltip(lbl2, "Tile icon assignment strategy:\n"
                      "Random: GenerateTileIconMapNormal (0x15058D8)\n"
                      "  Two-pointer scan, shuffled pool\n"
                      "Preset: DoTileBindingSet (0x1505B38)\n"
                      "  8 icon groups, round-robin deterministic")
        self.v_bind = tk.StringVar(value="random")
        ttk.Radiobutton(row2, text="Random", variable=self.v_bind, value="random",
                         style="D.TRadiobutton").pack(side="left", padx=3)
        ttk.Radiobutton(row2, text="Preset", variable=self.v_bind, value="preset",
                         style="D.TRadiobutton").pack(side="left", padx=3)

        self.v_validate = tk.BooleanVar(value=True)
        cb2 = ttk.Checkbutton(f3, text="Validate Solvability", variable=self.v_validate,
                               style="D.TCheckbutton")
        cb2.pack(anchor="w", pady=1)
        Tooltip(cb2, "ThereSolutionDescribe (0x159A9A0).\n"
                     "Check top layer has ≥1 matching triplet.\n"
                     "Retries up to 10 times if not solvable.")

        # ── Scoring Weights ──
        f4 = ttk.LabelFrame(self.left, text="Scoring Weights (GD)", style="D.TLabelframe", padding=6)
        f4.pack(fill="x", padx=6, pady=3)

        self.weight_vars = {}
        saved_w = load_scoring_weights()

        def weight_row(parent, label, key, tip=""):
            row = ttk.Frame(parent, style="D.TFrame")
            row.pack(fill="x", pady=1)
            lbl = ttk.Label(row, text=f"{label}:", style="D.TLabel", width=13)
            lbl.pack(side="left")
            if tip:
                Tooltip(lbl, tip)
            var = tk.DoubleVar(value=saved_w.get(key, DEFAULT_SCORING_WEIGHTS[key]))
            sc = tk.Scale(row, from_=0.0, to=10.0, resolution=0.1, orient="horizontal",
                          variable=var, bg="#1E1E2E", fg="#AAB", troughcolor="#2A2A3E",
                          highlightthickness=0, sliderrelief="flat",
                          font=("Consolas", 8), length=120, sliderlength=14,
                          command=lambda v, k=key: self._on_weight_change())
            sc.pack(side="left", fill="x", expand=True, padx=2)
            self.weight_vars[key] = var

        weight_row(f4, "X (Layout)", "X",
                   "Weight for Layout difficulty score.\n"
                   "Layout = avg recursive blocker depth of all tiles.")
        weight_row(f4, "Y (InterGroup)", "Y",
                   "Weight for Inter-Group score.\n"
                   "Sum of avg influence per tile type after stripping easy triples.")
        weight_row(f4, "Z (IntraGroup)", "Z",
                   "Weight for Intra-Group score.\n"
                   "Sum of (max-min)/count per type. Measures spread within each group.")
        weight_row(f4, "K (Cover100)", "K",
                   "Weight for 100% covered tile count.\n"
                   "Number of tiles completely hidden after stripping easy triples.")

        # ── Custom Triple Counts Per Type ──
        f5 = ttk.LabelFrame(self.left, text="Triple Counts Per Type", style="D.TLabelframe", padding=6)
        f5.pack(fill="x", padx=6, pady=3)

        self.v_custom_triples = tk.BooleanVar(value=False)
        cb_ct = ttk.Checkbutton(f5, text="Use Custom Triple Counts",
                                 variable=self.v_custom_triples, style="D.TCheckbutton",
                                 command=self._toggle_custom_triples)
        cb_ct.pack(anchor="w", pady=1)
        Tooltip(cb_ct, "When enabled, set specific triple count for each tile type.\n"
                       "Otherwise uses even distribution (total_groups / color_count).")

        self._triple_frame = ttk.Frame(f5, style="D.TFrame")
        self._triple_frame.pack(fill="x")
        self._triple_vars = []  # list of IntVar per type
        self._triple_widgets = []  # widgets to show/hide
        self._rebuild_triple_rows()

    def _toggle_custom_triples(self):
        self._rebuild_triple_rows()

    def _rebuild_triple_rows(self):
        # Clear old widgets
        for w in self._triple_widgets:
            w.destroy()
        self._triple_widgets.clear()
        self._triple_vars.clear()

        if not self.v_custom_triples.get():
            return

        cc = self.param_widgets.get("color_count")
        cc_val = cc.get() if cc else 4
        total_cells = self.board.total_cells() if self.board else 90
        default_triples = (total_cells // 3) // max(1, cc_val)

        for t in range(cc_val):
            row = ttk.Frame(self._triple_frame, style="D.TFrame")
            row.pack(fill="x", pady=1)
            self._triple_widgets.append(row)

            color = TILE_COLORS[t][0] if t < len(TILE_COLORS) else "#888"
            name = TILE_COLORS[t][2] if t < len(TILE_COLORS) else f"Type{t}"

            # Color swatch
            swatch = tk.Frame(row, bg=color, width=14, height=14)
            swatch.pack(side="left", padx=(2, 4))
            swatch.pack_propagate(False)

            lbl = ttk.Label(row, text=f"{name}:", style="D.TLabel", width=8)
            lbl.pack(side="left")

            var = tk.IntVar(value=default_triples)
            sp = tk.Spinbox(row, from_=0, to=200, textvariable=var, width=4,
                            bg="#16161E", fg="#AAB", font=("Consolas", 9))
            sp.pack(side="left", padx=2)
            self._triple_vars.append(var)

            ttk.Label(row, text="triples", style="S.TLabel").pack(side="left")

        # Info label
        info = ttk.Label(self._triple_frame, text=f"Total cells: {total_cells}  "
                         f"(need {total_cells // 3} triples)",
                         style="S.TLabel")
        info.pack(anchor="w", pady=(2, 0))
        self._triple_widgets.append(info)

    def _on_weight_change(self):
        if hasattr(self, 'weight_vars'):
            w = {k: v.get() for k, v in self.weight_vars.items()}
            save_scoring_weights(w)

    # ── Actions ──
    def _build_action_section(self):
        f = ttk.Frame(self.left, style="D.TFrame")
        f.pack(fill="x", padx=6, pady=6)

        btn = ttk.Button(f, text="GENERATE", style="Go.TButton", command=self._generate)
        btn.pack(fill="x", ipady=8, pady=(0,4))
        Tooltip(btn, "Run the full Tile Explorer level generation pipeline\n"
                     "with current parameters. Shortcut: Enter")
        self.bind("<Return>", lambda e: self._generate())

        row = ttk.Frame(f, style="D.TFrame")
        row.pack(fill="x", pady=2)
        ttk.Button(row, text="Re-shuffle", style="D.TButton",
                    command=self._generate).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(row, text="Clear", style="D.TButton",
                    command=self._clear).pack(side="left", fill="x", expand=True, padx=1)

        row2 = ttk.Frame(f, style="D.TFrame")
        row2.pack(fill="x", pady=2)
        ttk.Button(row2, text="Save Snapshot", style="D.TButton",
                    command=self._snapshot).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(row2, text="Export JSON", style="D.TButton",
                    command=self._export).pack(side="left", fill="x", expand=True, padx=1)

        # Solver section
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6)
        abtn = ttk.Button(f, text="ANALYZE SOLVABILITY", style="Go.TButton",
                           command=self._analyze)
        abtn.pack(fill="x", ipady=6, pady=(0,4))
        Tooltip(abtn, "Run 500 random playouts to find:\n"
                      "- Solutions count & solve rate\n"
                      "- Deadlock rate (tray full, no match)\n"
                      "- Steps to clear each layer\n"
                      "- Complexity score (0-100)\n"
                      "Requires tiles to be generated first.")

        row3 = ttk.Frame(f, style="D.TFrame")
        row3.pack(fill="x", pady=2)
        ttk.Label(row3, text="Simulations:", style="D.TLabel", width=11).pack(side="left")
        self.v_sims = tk.IntVar(value=500)
        tk.Spinbox(row3, from_=50, to=5000, increment=50, textvariable=self.v_sims,
                    width=6, bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)

        # Full Report (Difficulty Min/Max + Solvability merged)
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6)
        rbtn = ttk.Button(f, text="FULL REPORT", style="Go.TButton",
                           command=self._full_report)
        rbtn.pack(fill="x", ipady=6, pady=(0,4))
        Tooltip(rbtn, "Combined report: Difficulty (Min/Max batch)\n"
                      "+ Solvability (Monte Carlo playouts) in one panel.\n"
                      "Runs automatically after each successful generate\n"
                      "when 'Auto' is checked.")

        row4 = ttk.Frame(f, style="D.TFrame")
        row4.pack(fill="x", pady=2)
        ttk.Label(row4, text="Report Runs:", style="D.TLabel", width=11).pack(side="left")
        self.v_report_runs = tk.IntVar(value=50)
        tk.Spinbox(row4, from_=10, to=500, increment=10, textvariable=self.v_report_runs,
                    width=6, bg="#16161E", fg="#AAB", font=("Consolas", 9)).pack(side="left", padx=2)
        self.v_auto_report = tk.BooleanVar(value=True)
        tk.Checkbutton(row4, text="Auto after generate", variable=self.v_auto_report,
                        bg="#1A1A2E", fg="#AAB", selectcolor="#16161E",
                        activebackground="#1A1A2E", activeforeground="#CCD",
                        font=("Consolas", 9)).pack(side="left", padx=8)

        # MCP quick-access
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=6)
        mcp_btn = tk.Button(f, text="MCP / AI", bg="#1565C0", fg="#FFF",
                             font=("Consolas", 10, "bold"), relief="flat",
                             command=self._show_mcp_guide)
        mcp_btn.pack(fill="x", ipady=4)
        Tooltip(mcp_btn, "Open MCP / AI Connection Guide.\n"
                         "27 tools for Claude and AI agents to\n"
                         "control this tool programmatically.")

    # ── View Toolbar ──
    def _build_view_toolbar(self, parent):
        tb = ttk.Frame(parent, style="D.TFrame")
        tb.pack(fill="x", pady=(0,2))

        ttk.Label(tb, text="View:", style="D.TLabel").pack(side="left", padx=4)
        self.v_show = tk.StringVar(value="all")
        for v, t in [("all","All"), ("upto","Up to"), ("active","Active")]:
            ttk.Radiobutton(tb, text=t, variable=self.v_show, value=v,
                             style="D.TRadiobutton",
                             command=self._repaint).pack(side="left", padx=2)

        ttk.Label(tb, text="  Layer:", style="D.TLabel").pack(side="left")
        self.v_layer = tk.IntVar(value=0)
        sp = tk.Spinbox(tb, from_=0, to=15, textvariable=self.v_layer, width=3,
                         bg="#16161E", fg="#AAB", font=("Consolas", 9), command=self._repaint)
        sp.pack(side="left", padx=2)

        ttk.Button(tb, text="Fit", style="D.TButton", width=4,
                    command=lambda: self.canvas.fit(self.board) if self.board else None
                    ).pack(side="right", padx=4)

        # 3D toggle
        self.v_3d = tk.BooleanVar(value=False)
        ttk.Checkbutton(tb, text="3D", variable=self.v_3d, style="D.TCheckbutton",
                         command=self._toggle_3d).pack(side="right", padx=4)

        # Play button
        play_btn = tk.Button(tb, text="PLAY", bg="#1B5E20", fg="#FFF",
                              font=("Consolas", 10, "bold"), relief="flat", padx=10,
                              command=self._open_play)
        play_btn.pack(side="right", padx=4)
        Tooltip(play_btn, "Open a playable triple-match game window.\n"
                          "Test the level with current tiles.\n"
                          "3 buffs: Shuffle, Undo, +1 Slot")

        # Edit buttons
        ttk.Button(tb, text="Edit All", style="D.TButton",
                    command=lambda: self._open_editor("all")).pack(side="right", padx=2)
        ttk.Button(tb, text="Edit Layer", style="D.TButton",
                    command=lambda: self._open_editor("active")).pack(side="right", padx=2)
        ttk.Button(tb, text="Edit Pick...", style="D.TButton",
                    command=lambda: self._open_editor("pick")).pack(side="right", padx=2)

    # ── Stats Panel ──
    def _build_stats_panel(self, parent):
        ttk.Label(parent, text="RESULTS", style="H.TLabel").pack(anchor="w", padx=8, pady=(8,2))

        self.stats_text = tk.Text(parent, bg="#16161E", fg="#AAB", font=("Consolas", 9),
                                   wrap="word", borderwidth=0)
        self.stats_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.stats_text.tag_configure("header", foreground="#5DADE2", font=("Consolas", 10, "bold"))
        self.stats_text.tag_configure("good", foreground="#58D68D")
        self.stats_text.tag_configure("warn", foreground="#F39C12")
        self.stats_text.tag_configure("bad", foreground="#E74C3C")
        self.stats_text.tag_configure("dim", foreground="#556")

        # Pin button
        pin_row = ttk.Frame(parent, style="D.TFrame")
        pin_row.pack(fill="x", padx=8, pady=4)
        ttk.Button(pin_row, text="Pin Current", style="D.TButton",
                    command=self._pin_current).pack(side="left", fill="x", expand=True, padx=1)
        ttk.Button(pin_row, text="View List", style="D.TButton",
                    command=self._show_pinned_list).pack(side="left", fill="x", expand=True, padx=1)

        # History section
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=8, pady=4)
        ttk.Label(parent, text="HISTORY", style="H.TLabel").pack(anchor="w", padx=8)
        self.history_text = tk.Text(parent, bg="#16161E", fg="#778", font=("Consolas", 8),
                                     wrap="word", borderwidth=0, height=6)
        self.history_text.pack(fill="both", expand=True, padx=4, pady=4)

    # ─── Actions ───

    def _sync_params(self):
        for attr, var in self.param_widgets.items():
            setattr(self.engine, attr, var.get())
        self.engine.style_mode = self.v_style.get()
        self.engine.extended = self.v_ext.get()
        self.engine.binding = self.v_bind.get()
        self.engine.validate = self.v_validate.get()
        # Auto-adjust style_mode for high color counts
        cc = self.engine.color_count
        if cc > 6 and self.engine.style_mode != 3:
            self.engine.style_mode = 3
            self.engine.extended = True
        elif cc > 5 and self.engine.style_mode == 0:
            self.engine.style_mode = 7
        # Custom triple counts
        if hasattr(self, 'v_custom_triples') and self.v_custom_triples.get() and self._triple_vars:
            self.engine.custom_triples = {i: v.get() for i, v in enumerate(self._triple_vars)}
        else:
            self.engine.custom_triples = None

    def _generate(self):
        if not self.board: return
        self._sync_params()
        stats = self.engine.generate(self.board)
        # Compute new difficulty score
        try:
            w = {k: v.get() for k, v in self.weight_vars.items()} if hasattr(self, 'weight_vars') else None
            ns = DifficultyScorer.compute_full_score(self.board, weights=w)
            stats.update({"new_" + k: v for k, v in ns.items()})
        except Exception:
            pass
        self.canvas.paint()
        self._show_stats(stats)
        self._add_history(stats)
        self._update_main_layer_list()
        self._update_status()
        logger.log_event("generate", board=self.board.name,
                         total=stats.get("total"), solvable=stats.get("solvable"),
                         final_score=stats.get("new_final_score"))

        # Auto-run full report after successful generate
        auto = getattr(self, 'v_auto_report', None)
        if auto is not None and auto.get() and stats.get("total", 0) > 0:
            self.after(50, self._full_report)

    def _clear(self):
        if self.board:
            self.board.clear_tiles()
            self.canvas.paint()
            self._update_status()

    def _full_report(self):
        """Combined Difficulty (Min/Max batch) + Solvability report."""
        if not self.board:
            return
        has_tiles = any(c.tile_id >= 0 for c in self.board.all_cells())
        if not has_tiles:
            self._generate()
            return  # _generate will re-invoke via auto-report
        self._sync_params()

        w = {k: v.get() for k, v in self.weight_vars.items()} if hasattr(self, 'weight_vars') else None
        n_runs = self.v_report_runs.get() if hasattr(self, 'v_report_runs') else 50
        sims = self.v_sims.get() if hasattr(self, 'v_sims') else 500

        self.status.set(f"Full report — batch scoring ({n_runs} runs)...")
        self.update_idletasks()
        summary = DifficultyScorer.batch_score(self.board, self.engine, weights=w, n_runs=n_runs)

        self.status.set(f"Full report — solvability ({sims} sims)...")
        self.update_idletasks()
        try:
            solv = TileSolver.analyze(self.board, max_solutions=100, max_steps=sims)
        except Exception as ex:
            solv = {"error": str(ex)}

        self._render_full_report(summary, solv, n_runs, sims)
        self.status.set(f"Full report done — {n_runs} runs / {sims} sims")
        logger.log_event("full_report", board=self.board.name,
                         final_min=(summary.get("final_score") or {}).get("min"),
                         final_max=(summary.get("final_score") or {}).get("max"),
                         solve_rate=solv.get("solve_rate"),
                         deadlock_rate=solv.get("deadlock_rate"))

    def _render_full_report(self, summary, solv, n_runs, sims):
        t = self.stats_text
        t.delete("1.0", "end")

        # --- Section 1: Difficulty ---
        t.insert("end", "Difficulty (Min/Max)\n", "header")
        t.insert("end", f"Runs: {summary.get('n_runs', n_runs)}   "
                         f"Avg Stripped: {summary.get('stripped_avg', 0)}\n\n")
        for key, label in [("layout", "Layout"), ("inter_group", "InterGroup"),
                           ("intra_group", "IntraGroup"), ("cover100", "Cover100"),
                           ("final_score", "FINAL SCORE")]:
            d = summary.get(key, {})
            if isinstance(d, dict):
                tag = "header" if key == "final_score" else None
                line = f"  {label:<11} min={d.get('min','?'):<7} max={d.get('max','?'):<7} avg={d.get('avg','?')}\n"
                if tag:
                    t.insert("end", line, tag)
                else:
                    t.insert("end", line)

        # --- Section 2: Solvability ---
        t.insert("end", "\nSolvability\n", "header")
        if solv.get("error"):
            t.insert("end", f"  Error: {solv['error']}\n", "bad")
        else:
            t.insert("end", f"  Simulations: {solv.get('total_simulations', sims)}\n")
            sr = solv.get('solve_rate', 0)
            t.insert("end", f"  Solve Rate: {sr}%\n",
                     "good" if sr > 50 else "warn" if sr > 10 else "bad")
            dr = solv.get('deadlock_rate', 0)
            t.insert("end", f"  Deadlock:   {dr}%\n",
                     "bad" if dr > 50 else "warn" if dr > 20 else "good")
            if solv.get('min_moves'):
                t.insert("end", f"  Moves: min={solv['min_moves']} "
                                f"avg={solv['avg_moves']} max={solv['max_moves']}\n")
            cs = solv.get('complexity_score', 0)
            cl = solv.get('complexity_label', '?')
            t.insert("end", f"  Complexity: {cs}/100 [{cl}]\n",
                     "good" if cs < 35 else "warn" if cs < 65 else "bad")

        # --- Section 3: Verdict ---
        t.insert("end", "\nVerdict\n", "header")
        fmax = (summary.get("final_score") or {}).get("max", 0) or 0
        fmin = (summary.get("final_score") or {}).get("min", 0) or 0
        sr = solv.get('solve_rate', 0) if not solv.get("error") else -1
        dr = solv.get('deadlock_rate', 0) if not solv.get("error") else -1

        if sr < 0:
            verdict = ("Solvability check failed — difficulty only", "warn")
        elif sr == 0:
            verdict = ("IMPOSSIBLE — no random playout solved. Check layout.", "bad")
        elif sr > 95 and fmax < 15:
            verdict = ("TRIVIAL — always solves, very low difficulty.", "warn")
        elif dr > 60:
            verdict = ("FRUSTRATING — high deadlock rate, tight tray.", "bad")
        elif 20 <= fmin and fmax <= 80 and 20 <= sr <= 90:
            verdict = ("BALANCED — good difficulty + playable.", "good")
        elif fmax >= 80 and sr >= 20:
            verdict = ("HARD — challenging but playable.", "good")
        elif fmax >= 80 and sr < 20:
            verdict = ("TOO HARD — low solve rate. Consider easing.", "bad")
        else:
            verdict = (f"Score {fmin}-{fmax}, solve {sr}%.", None)

        t.insert("end", f"  {verdict[0]}\n", verdict[1] if verdict[1] else "")

    def _analyze(self):
        if not self.board:
            return
        # Ensure tiles are generated first
        has_tiles = any(c.tile_id >= 0 for c in self.board.all_cells())
        if not has_tiles:
            self._generate()

        self.status.set("Analyzing solvability... (this may take a few seconds)")
        self.update_idletasks()

        result = TileSolver.analyze(self.board, max_solutions=100,
                                     max_steps=self.v_sims.get())
        self._show_solver_stats(result)
        self._update_status()
        logger.log_event("analyze", board=self.board.name,
                         solve_rate=result.get("solve_rate"),
                         deadlock_rate=result.get("deadlock_rate"))

    def _show_solver_stats(self, r):
        t = self.stats_text
        t.delete("1.0", "end")

        t.insert("end", "Solvability Analysis\n", "header")
        t.insert("end", f"Simulations: {r['total_simulations']}\n")

        sr = r.get('solve_rate', 0)
        t.insert("end", f"Solve Rate: {sr}%\n", "good" if sr > 50 else "warn" if sr > 10 else "bad")
        t.insert("end", f"Solutions Found: {r['solutions_found']}\n")

        dr = r.get('deadlock_rate', 0)
        t.insert("end", f"Deadlock Rate: {dr}%\n", "bad" if dr > 50 else "warn" if dr > 20 else "good")

        if r.get('min_moves'):
            t.insert("end", f"\nMoves to Solve\n", "header")
            t.insert("end", f"  Minimum: {r['min_moves']}\n")
            t.insert("end", f"  Average: {r['avg_moves']}\n")
            t.insert("end", f"  Maximum: {r['max_moves']}\n")

        t.insert("end", f"\nComplexity\n", "header")
        cs = r.get('complexity_score', 0)
        cl = r.get('complexity_label', '?')
        bar = "|" * (cs // 2) + "." * (50 - cs // 2)
        tag = "good" if cs < 35 else "warn" if cs < 65 else "bad"
        t.insert("end", f"  Score: {cs}/100 [{cl}]\n", tag)
        t.insert("end", f"  {bar}\n", "dim")

        t.insert("end", f"\nLayer-by-Layer Clear\n", "header")
        la = r.get('layer_analysis', {})
        for li in sorted(la.keys()):
            info = la[li]
            avg = info['avg_moves']
            rate = info['clear_rate']
            nc = info['cells']
            if avg >= 0:
                t.insert("end", f"  L{li}: {nc:3d} cells | avg {avg:5.1f} moves | "
                                f"cleared {rate}%\n")
            else:
                t.insert("end", f"  L{li}: {nc:3d} cells | never cleared\n", "bad")

        # Summary
        t.insert("end", f"\nInterpretation\n", "header")
        if sr > 80:
            t.insert("end", "  Level is very solvable - most random play wins.\n", "good")
        elif sr > 40:
            t.insert("end", "  Level is moderately solvable - needs some strategy.\n", "warn")
        elif sr > 10:
            t.insert("end", "  Level is hard - many paths lead to deadlock.\n", "warn")
        elif sr > 0:
            t.insert("end", "  Level is very hard - few solutions exist.\n", "bad")
        else:
            t.insert("end", "  Level may be UNSOLVABLE with current tiles!\n", "bad")

        if dr > 60:
            t.insert("end", f"  High deadlock rate ({dr}%) - tray fills up easily.\n", "bad")
            t.insert("end", "  Consider: fewer colors or fewer layers.\n", "dim")

        # New scoring in solver results
        if r.get("new_final_score") is not None:
            t.insert("end", f"\nNew Difficulty Score\n", "header")
            t.insert("end", f"  Layout:     {r.get('new_layout', 0)}\n")
            t.insert("end", f"  InterGroup: {r.get('new_inter_group', 0)}\n")
            t.insert("end", f"  IntraGroup: {r.get('new_intra_group', 0)}\n")
            t.insert("end", f"  Cover 100%: {r.get('new_cover100', 0)}\n")
            t.insert("end", f"  Stripped:   {r.get('new_stripped', 0)} triples\n")
            t.insert("end", f"  FINAL:      {r.get('new_final_score', 0)}\n", "header")

    def _load_default(self):
        files = list_level_files()
        if files:
            self.board = load_board(files[0], 0)
            if self.board:
                cnt = get_board_count(files[0])
                self.lbl_bcount.config(text=f"/ {cnt}")
                self.sp_board.config(to=max(0, cnt-1))
        if not self.board:
            self.board = make_sample_board()
        self._update_board_info()
        self.after(100, lambda: self.canvas.fit(self.board))

    def _load_board(self):
        fn = self.v_file.get()
        idx = self.v_bidx.get()
        # If we have an imported single file, use its full path
        if hasattr(self, '_imported_file') and self._imported_file and os.path.basename(self._imported_file) == fn:
            b = load_board(self._imported_file, idx)
        else:
            b = load_board(fn, idx)
        if b:
            self.board = b
            self.canvas.board = b
            self._update_board_info()
            self.canvas.fit(b)
            logger.log_event("board_load", file=fn, board_idx=idx,
                             cells=b.total_cells(), layers=len(b.layers))
        else:
            messagebox.showwarning("Error", f"Cannot load {fn} board {idx}")

    def _import_file(self):
        """Import a single JSON file from anywhere."""
        path = filedialog.askopenfilename(
            title="Import Board File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=get_levels_dir())
        if not path:
            return
        b = load_board(path, 0)
        if b:
            self.board = b
            self.canvas.board = b
            self._update_board_info()
            self.canvas.fit(b)
            # Update file combo to show this file
            self.v_file.set(os.path.basename(path))
            cnt = get_board_count(path)
            self.lbl_bcount.config(text=f"/ {cnt}")
            self.sp_board.config(to=max(0, cnt - 1))
            self.v_bidx.set(0)
            self.lbl_folder.config(text=f"File: {os.path.basename(path)}")
            self.status.set(f"Imported: {path}")
            # Store directory for subsequent loads from this file
            self._imported_file = path
        else:
            messagebox.showwarning("Error", f"Cannot read board from:\n{path}")

    def _import_folder(self):
        """Switch level source to a different folder."""
        d = filedialog.askdirectory(
            title="Choose Level Folder",
            initialdir=get_levels_dir())
        if not d:
            return
        # Check if folder has any JSON files
        jsons = [f for f in os.listdir(d) if f.endswith(".json") and not f.startswith("_")]
        if not jsons:
            messagebox.showwarning("Empty Folder", f"No JSON files found in:\n{d}")
            return
        # Switch to new folder
        set_levels_dir(d)
        self.lbl_folder.config(text=f"Folder: {os.path.basename(d)}")
        # Refresh file list
        files = list_level_files()
        self.file_combo.config(values=files)
        if files:
            self.v_file.set(files[0])
            self._on_file_change()
            self._load_board()
        self.status.set(f"Folder: {d} ({len(jsons)} files)")
        self._imported_file = None  # clear single-file mode

    def _on_file_change(self, _=None):
        fn = self.v_file.get()
        cnt = get_board_count(fn)
        self.lbl_bcount.config(text=f"/ {cnt}")
        self.sp_board.config(to=max(0, cnt-1))
        self.v_bidx.set(0)

    def _nav_board(self, delta):
        new = self.v_bidx.get() + delta
        fn = self.v_file.get()
        cnt = get_board_count(fn)
        if 0 <= new < cnt:
            self.v_bidx.set(new)
            self._load_board()

    def _random_board(self):
        files = list_level_files()
        if not files: return
        fn = random.choice(files)
        cnt = get_board_count(fn)
        if cnt <= 0: return
        self.v_file.set(fn)
        self._on_file_change()
        self.v_bidx.set(random.randint(0, cnt-1))
        self._load_board()

    def _apply_preset(self, name):
        p = DIFFICULTY_PRESETS[name]
        mapping = {
            "level_number": "level_number", "color_count": "color_count",
            "hard_code": "hard_code", "less_type": "less_type",
            "up_easy": "up_easy", "top2_easy": "top2_easy",
            "top3_easy": "top3_easy", "top4_easy": "top4_easy",
            "distance": "distance", "val_replace": "val_replace",
            "val_mode": "val_mode",
        }
        for ui_key, eng_key in mapping.items():
            if eng_key in self.param_widgets and ui_key in p:
                self.param_widgets[eng_key].set(p[ui_key])
        self.v_style.set(p["style_mode"])
        self.v_ext.set(p["extended"])
        self.v_bind.set(p["binding"])

    def _update_board_info(self):
        if self.board:
            nl = len(self.board.layers)
            nc = self.board.total_cells()
            self.lbl_board_info.config(text=f"{nl} layers, {nc} cells")
            self.canvas.board = self.board
            self.v_layer.set(0)
            self._update_main_layer_list()
        self._update_status()

    def _update_main_layer_list(self):
        """Visual layer list in main scene — color swatch + name + click to select."""
        for w in self.main_layer_frame.winfo_children():
            w.destroy()
        if not self.board:
            return
        active = self.v_layer.get()
        for i, layer in enumerate(self.board.layers):
            is_active = (i == active)
            color = LAYER_COLORS[i % len(LAYER_COLORS)]

            row = tk.Frame(self.main_layer_frame, bg="#262636" if is_active else "#1E1E2E",
                            cursor="hand2", padx=3, pady=2)
            row.pack(fill="x", pady=1)
            row.bind("<Button-1>", lambda e, idx=i: self._select_main_layer(idx))

            # Color swatch
            sw = tk.Canvas(row, width=14, height=14, bg=color, highlightthickness=0)
            sw.pack(side="left", padx=(2, 6))
            sw.bind("<Button-1>", lambda e, idx=i: self._select_main_layer(idx))

            # Layer info
            fg = "#FFF" if is_active else "#889"
            font = ("Consolas", 9, "bold") if is_active else ("Consolas", 9)
            # Count tile types in this layer
            types = set(c.tile_id for c in layer.cells if c.tile_id >= 0)
            type_str = f"{len(types)}t" if types else ""

            lbl = tk.Label(row, text=f"L{i}  {len(layer.cells):3d} cells  {type_str}",
                            bg=row.cget("bg"), fg=fg, font=font)
            lbl.pack(side="left", fill="x")
            lbl.bind("<Button-1>", lambda e, idx=i: self._select_main_layer(idx))

            # Active marker
            if is_active:
                tk.Label(row, text="\u25c0", bg=row.cget("bg"), fg="#5DADE2",
                          font=("Consolas", 9)).pack(side="right", padx=2)

    def _select_main_layer(self, idx):
        self.v_layer.set(idx)
        self._update_main_layer_list()
        self._repaint()

    def _update_status(self):
        if self.board:
            assigned = sum(1 for c in self.board.all_cells() if c.tile_id >= 0)
            self.status.set(f"{self.board.name}  |  {self.board.total_cells()} cells  |  "
                            f"{assigned} assigned  |  {len(self.board.layers)} layers")

    def _repaint(self):
        self.canvas.show = self.v_show.get()
        self.canvas.active_layer = self.v_layer.get()
        self.canvas.paint()

    def _open_play(self):
        if not self.board:
            return
        has_tiles = any(c.tile_id >= 0 for c in self.board.all_cells())
        if not has_tiles:
            self._generate()
        PlayWindow(self, self.board)

    def _toggle_3d(self):
        self.canvas.view_3d = self.v_3d.get()
        if self.board:
            self.canvas.fit(self.board)  # re-fit because projection changes
        else:
            self.canvas.paint()

    def _open_editor(self, mode="all"):
        if not self.board:
            return

        if mode == "active":
            # Send only the active layer
            layers = [self.v_layer.get()]
        elif mode == "pick":
            # Show layer picker dialog
            layers = self._show_layer_picker()
            if not layers:
                return  # user cancelled
        else:
            layers = list(range(len(self.board.layers)))

        EditWindow(self, self.board, layers, self._on_edit_save)

    def _show_layer_picker(self):
        """Popup dialog to let user select which layers to send to editor."""
        if not self.board:
            return []

        dlg = tk.Toplevel(self)
        dlg.title("Select Layers to Edit")
        dlg.geometry("280x400")
        dlg.configure(bg="#1E1E2E")
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(dlg, text="Select layers to edit:", bg="#1E1E2E", fg="#FFF",
                  font=("Consolas", 10, "bold")).pack(anchor="w", padx=12, pady=(12, 6))

        # Checkboxes for each layer
        layer_vars = []
        for i, layer in enumerate(self.board.layers):
            color = LAYER_COLORS[i % len(LAYER_COLORS)]
            var = tk.BooleanVar(value=True)
            row = tk.Frame(dlg, bg="#1E1E2E")
            row.pack(fill="x", padx=12, pady=2)

            swatch = tk.Canvas(row, width=16, height=16, bg=color, highlightthickness=0)
            swatch.pack(side="left", padx=(0, 6))

            cb = tk.Checkbutton(row, text=f"Layer {i}  ({len(layer.cells)} cells)",
                                 variable=var, bg="#1E1E2E", fg="#AAB",
                                 selectcolor="#2D2D44", font=("Consolas", 10),
                                 activebackground="#1E1E2E", activeforeground="#FFF")
            cb.pack(side="left")
            layer_vars.append(var)

        # Select all / none
        btn_row = tk.Frame(dlg, bg="#1E1E2E")
        btn_row.pack(fill="x", padx=12, pady=6)
        tk.Button(btn_row, text="All", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=lambda: [v.set(True) for v in layer_vars]
                   ).pack(side="left", padx=2)
        tk.Button(btn_row, text="None", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=lambda: [v.set(False) for v in layer_vars]
                   ).pack(side="left", padx=2)
        tk.Button(btn_row, text="Top 2", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=lambda: [v.set(i >= len(layer_vars)-2) for i, v in enumerate(layer_vars)]
                   ).pack(side="left", padx=2)
        tk.Button(btn_row, text="Bottom 2", bg="#2D2D44", fg="#CCD", font=("Consolas", 9),
                   relief="flat", command=lambda: [v.set(i < 2) for i, v in enumerate(layer_vars)]
                   ).pack(side="left", padx=2)

        # OK / Cancel
        result = []

        def on_ok():
            for i, var in enumerate(layer_vars):
                if var.get():
                    result.append(i)
            dlg.destroy()

        def on_cancel():
            dlg.destroy()

        ok_row = tk.Frame(dlg, bg="#1E1E2E")
        ok_row.pack(fill="x", padx=12, pady=12)
        tk.Button(ok_row, text="Open Editor", bg="#1B5E20", fg="#FFF",
                   font=("Consolas", 10, "bold"), relief="flat", padx=16,
                   command=on_ok).pack(side="left", padx=4)
        tk.Button(ok_row, text="Cancel", bg="#555", fg="#FFF",
                   font=("Consolas", 9), relief="flat", padx=12,
                   command=on_cancel).pack(side="left", padx=4)

        dlg.wait_window()
        return result

    def _on_edit_save(self):
        """Called when editor saves — regenerate tiles + update stats."""
        if not self.board:
            return
        self.canvas.board = self.board
        self._update_board_info()
        self._generate()  # re-generate tiles with current params
        self.canvas.fit(self.board)

    def _pin_current(self):
        """Pin current board to favorites list."""
        if not self.board:
            self.status.set("No board to pin")
            return
        fname = self.v_file.get()
        bidx = self.v_bidx.get()

        # Build stats from last generation
        stats = {}
        if self.history:
            last = self.history[-1]
            # history items are generation stats dicts
            stats = {
                "cells": last.get("total", self.board.total_cells()),
                "layers": len(self.board.layers),
                "eff_cc": last.get("eff_cc", 0),
                "solvable": last.get("solvable", False),
            }

        # Quick solvability if not yet analyzed
        if "solve_rate" not in stats:
            has_tiles = any(c.tile_id >= 0 for c in self.board.all_cells())
            if has_tiles:
                r = TileSolver.analyze(self.board, max_steps=50)
                stats["solve_rate"] = r.get("solve_rate", 0)
                stats["complexity_label"] = r.get("complexity_label", "?")

        meta.add_pinned(fname, bidx, stats=stats)
        self.status.set(f"Pinned: {fname} #{bidx}")

    def _show_pinned_list(self):
        """Open Pinned List window."""
        PinnedListWindow(self)

    def _show_stats(self, s):
        t = self.stats_text
        t.delete("1.0", "end")

        t.insert("end", "Generation Result\n", "header")
        tsi, ecc = s.get("tile_set", "?"), s.get("eff_cc", "?")
        t.insert("end", f"Tile Set Index: {tsi}\n")
        t.insert("end", f"Effective Colors: {ecc}\n")
        t.insert("end", f"Total Cells: {s['total']}\n")
        t.insert("end", f"HardBg Tiles: {s.get('bg_tiles', 0)}\n")

        sol = s.get("solvable", False)
        t.insert("end", f"Solvable: {'YES' if sol else 'NO'}\n", "good" if sol else "bad")

        m3 = s.get("multiples_of_3", False)
        t.insert("end", f"All x3: {'YES' if m3 else 'NO'}\n", "good" if m3 else "warn")

        t.insert("end", "\nTile Distribution\n", "header")
        dist = s.get("dist", {})
        total = s["total"]
        for tid in sorted(dist.keys()):
            cnt = dist[tid]
            pct = cnt / total * 100 if total else 0
            name = TILE_COLORS[tid][2] if tid < len(TILE_COLORS) else f"Type{tid}"
            bar = "█" * int(pct / 2)
            x3 = "  ok" if cnt % 3 == 0 else "  !"
            tag = "good" if cnt % 3 == 0 else "warn"
            t.insert("end", f"  {name:<7} {cnt:3d} ({pct:4.1f}%) {bar}{x3}\n", tag)

        t.insert("end", "\nPer Layer\n", "header")
        for li, ls in sorted(s.get("layers", {}).items()):
            t.insert("end", f"  L{li}: {ls['cells']:3d} cells, {ls['types']} types\n")

        # New Difficulty Score
        if s.get("new_final_score") is not None:
            t.insert("end", "\nDifficulty Score (New)\n", "header")
            t.insert("end", f"  Layout:     {s.get('new_layout', 0)}\n")
            t.insert("end", f"  InterGroup: {s.get('new_inter_group', 0)}\n")
            t.insert("end", f"  IntraGroup: {s.get('new_intra_group', 0)}\n")
            t.insert("end", f"  Cover 100%: {s.get('new_cover100', 0)}\n")
            t.insert("end", f"  Stripped:   {s.get('new_stripped', 0)} triples\n")
            t.insert("end", f"  Remaining:  {s.get('new_remaining_tiles', 0)} tiles\n")
            w = s.get("new_weights", {})
            t.insert("end", f"  Weights:    X={w.get('X','?')} Y={w.get('Y','?')} "
                     f"Z={w.get('Z','?')} K={w.get('K','?')}\n")
            t.insert("end", f"  FINAL:      {s.get('new_final_score', 0)}\n", "header")

        # Active knobs summary
        t.insert("end", "\nActive Knobs\n", "header")
        e = self.engine
        knobs = []
        if e.less_type: knobs.append("LessTypeUpDownSide")
        if e.up_easy: knobs.append("UpLayerEasy")
        if e.distance > 0 and e.level_number > 100: knobs.append(f"TileDistance={e.distance}")
        if e.top2_easy: knobs.append("TopTwoLayerEasy")
        if e.val_replace and e.level_number >= 51:
            knobs.append(f"ValueReplace(mode={e.val_mode}, hash={e.level_number%10})")
        if not knobs: knobs.append("None")
        for k in knobs:
            t.insert("end", f"  {k}\n")

    def _add_history(self, s):
        self.history.append(s)
        if len(self.history) > 20:
            self.history.pop(0)

        ht = self.history_text
        ht.delete("1.0", "end")
        for i, h in enumerate(reversed(self.history[-10:])):
            cc = h.get("eff_cc", "?")
            sol = "ok" if h.get("solvable") else "NO"
            dist = h.get("dist", {})
            types = len(dist)
            ht.insert("end", f"#{len(self.history)-i}: cc={cc} types={types} sol={sol} "
                              f"dist={dict(sorted(dist.items()))}\n")

    def _pick_export_dir(self):
        """Let user choose export folder. Remembers last choice."""
        d = filedialog.askdirectory(title="Choose Export Folder",
                                      initialdir=self.export_dir)
        if d:
            self.export_dir = d
        return d

    def _snapshot(self):
        if not self.board: return
        d = self._pick_export_dir()
        if not d: return
        data = {
            "board": self.board.name,
            "params": {k: v.get() for k, v in self.param_widgets.items()},
            "style_mode": self.v_style.get(),
            "extended": self.v_ext.get(),
            "binding": self.v_bind.get(),
            "tiles": [(c.x, c.y, c.layer_idx, c.tile_id) for c in self.board.all_cells()],
        }
        fname = f"snapshot_{self.engine.level_number}_{self.engine.color_count}c.json"
        path = os.path.join(d, fname)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        self.status.set(f"Saved: {path}")

    def _export(self):
        if not self.board: return
        d = self._pick_export_dir()
        if not d: return
        # Export with full metadata
        solver_r = None
        if self.history:
            solver_r = self.history[-1]
        dp, mp = meta.export_with_metadata(self.board, d, self.engine, solver_r)
        meta.build_collection_index(d)
        self.status.set(f"Exported: {dp} + metadata")

    def _export_stones(self):
        """Export current board in stones/stacks format (Format 4)."""
        if not self.board:
            messagebox.showwarning("Export", "No board loaded.")
            return
        # Check tiles are assigned
        has_tiles = any(c.tile_id >= 0 for c in self.board.all_cells())
        if not has_tiles:
            messagebox.showwarning("Export", "Generate tiles first before exporting stones format.")
            return

        path = filedialog.asksaveasfilename(
            title="Export Stones Format",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"{self.board.name}_stones.json",
        )
        if not path:
            return

        data = export_board_stones_format(self.board)
        try:
            with open(path, "w") as f:
                json.dump(data, f, separators=(",", ":"))
            self.status.set(f"Exported stones format: {os.path.basename(path)}")
            logger.log_event("export", format="stones", path=path, board=self.board.name)
        except OSError as e:
            logger.log_error("export_stones", str(e))
            messagebox.showerror("Export Error", str(e))


if __name__ == "__main__":
    App().mainloop()
