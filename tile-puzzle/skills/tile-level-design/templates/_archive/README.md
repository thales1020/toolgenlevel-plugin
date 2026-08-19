# Archived templates — superseded, kept for provenance only

Not run by any current script/doc-recommended workflow. Do not use for new work; each has a
confirmed successor (not a guess — see the evidence below before reaching for one of these):

- `find_hybrid_custom.py` → superseded by `find_hybrid_custom_fast.py` (its own docstring:
  "Fixes bottleneck from find_hybrid_custom.py"; the `_fast` file is what `gen_all_9.py` calls).
- `difficulty_minmax.py`, `difficulty_minmax_combined.py` → superseded by
  `difficulty_minmax_solvable_parallel.py`, the canonical sweep script per
  `docs/CLAUDE.md` §4 ("The canonical script is `difficulty_minmax_solvable_parallel.py`").
- `gen_5_patterns.py` → functionally absorbed by `scripts/gen_pattern.py --pattern N`
  ("5 patterns" generalized to 6, parameterized on any layout). Not cited as an active
  recommendation anywhere; only appears in two docs as a historical benchmark number
  (`feedback_search_speed.md`, `docs/LEVEL_DESIGN_GUIDE.md`), which stays valid as history
  regardless of this file's location.

If a doc ever tells you to run one of these, that doc is stale — prefer the successor above.
