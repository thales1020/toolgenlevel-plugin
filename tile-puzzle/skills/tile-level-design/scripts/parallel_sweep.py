"""parallel_sweep — run a picklable worker over items across CPU cores and return the LOWEST-INDEX item
whose result satisfies a predicate (ordered early-stop), plus every result seen up to it.

This is the generic, game-agnostic core of "parallelize a seed/candidate sweep but keep the serial
early-stop semantics exactly." It exists so the correctness-critical invariants live in ONE tested place:

  * **Ordered early-stop = deterministic winner.** Results are consumed via `imap` in *submission order*,
    so the first result that satisfies `predicate` is the lowest-index one — identical to a serial
    `for item in items: ... if ok: break`. The winner does NOT depend on which worker finishes first.
  * **PYTHONHASHSEED guard.** Any generator whose output depends on hash randomization (e.g. dict/set
    iteration order) produces DIFFERENT results in a fresh spawned worker unless PYTHONHASHSEED is pinned
    in the environment. `first_match` refuses to run when it is unset (override with require_hashseed=False
    only if your worker is hash-order-independent), so a parallel run can't silently diverge from serial.

Caller contract:
  * `worker` must be a TOP-LEVEL (importable, picklable) callable `worker(item) -> result`. A lambda or a
    closure will fail to pickle under the 'spawn' start method (Windows/macOS default). Pack per-item
    context INTO each `item` (a tuple/dict), or bind fixed context with `functools.partial` of a
    top-level function.
  * `worker` must NOT raise — catch inside and return a sentinel result (mirror a serial loop that skips
    a failing item), because an exception in `imap` aborts the whole sweep.
  * `predicate(result) -> bool` and the optional `on_result(index, result)` run in the PARENT process, so
    they MAY be closures (handy for logging / accumulating "closest").

Returns `(match, seen)`:
  * `match` = the result of the lowest-index item with `predicate(result)` True, or None if none match.
  * `seen`  = results in index order up to & including the match (or all items if nothing matched) — the
    exact set a serial early-stop loop would have observed, so callers can derive e.g. a "closest" pick.
"""
import os
import multiprocessing as mp


def first_match(worker, items, predicate, on_result=None, nproc=None, require_hashseed=True):
    if require_hashseed and not os.environ.get("PYTHONHASHSEED"):
        raise RuntimeError(
            "parallel_sweep.first_match requires a pinned PYTHONHASHSEED (e.g. PYTHONHASHSEED=0) so spawned "
            "workers reproduce the serial run's results; refusing to run non-reproducibly. Pass "
            "require_hashseed=False only if the worker's output is independent of hash randomization.")
    items = list(items)
    if not items:
        return None, []
    if nproc is None:
        nproc = max(1, (os.cpu_count() or 2) - 1)

    seen = []
    match = None
    with mp.Pool(processes=min(nproc, len(items))) as pool:
        # chunksize=1 + imap keeps consumption strictly in submission order → first predicate-True is the
        # lowest-index match. Breaking lets the Pool context terminate remaining in-flight workers.
        for idx, result in enumerate(pool.imap(worker, items, chunksize=1)):
            if on_result is not None:
                on_result(idx, result)
            seen.append(result)
            if predicate(result):
                match = result
                break
    return match, seen
