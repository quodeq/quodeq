"""Process-lived memo of resumable per-file findings tallies.

Split out of ``_scan_progress_dims.py`` to keep that module under the size
ratchet's 300-line cap. ``LiveTallyMemo`` wraps the bounded
``(evidence file, suppression state) -> _GuardedTally`` mapping that used to
be the bare module globals ``_LIVE_TALLIES``/``_LIVE_TALLIES_LOCK`` there; see
``_scan_progress_dims.live_tally`` for why the memo exists at all (a live
progress poll resumes an ``IncrementalTally`` instead of re-parsing an
evidence file from byte 0 on every tick).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from quodeq.services.wiring import FindingTally, IncrementalTally
from quodeq.shared.lru import LRUDict

# Bounds the number of memoized tallies: a run polled by several dashboard
# threads, times a handful of concurrently-open runs, stays well under this
# before the coldest entries start evicting.
LIVE_TALLY_MEMO_SIZE = 256


@dataclass
class _GuardedTally:
    """One memoized ``IncrementalTally`` plus the lock that serialises it.

    A tally is mutable state (offset, dedup set, counters) shared by every
    poll of the same run and suppression state, so concurrent ``advance()``
    calls on ONE tally have to be serialised. Its own lock, rather than the
    memo's: two polls of different runs then read their files in parallel.
    """

    tally: IncrementalTally
    lock: threading.Lock = field(default_factory=threading.Lock)

    def advance(self) -> FindingTally:
        with self.lock:
            return self.tally.advance()


class LiveTallyMemo:
    """Process-lived, bounded memo of ``_GuardedTally`` objects.

    One instance lives per process (see ``services/_process_owners.py``);
    tests build their own for isolation instead of resetting global state.
    The memo's own lock guards the check-build-store sequence in
    ``get_or_build``, not a tally's ``advance()`` -- see ``_GuardedTally``.
    """

    def __init__(self, size: int = LIVE_TALLY_MEMO_SIZE) -> None:
        self._memo: LRUDict = LRUDict(size)
        self._lock = threading.Lock()

    def get_or_build(self, key: tuple, build: Callable[[], IncrementalTally]) -> _GuardedTally:
        """The memoized ``_GuardedTally`` for *key*, building it on a miss.

        *build* is called at most once per miss, under the memo's lock, so
        two racing callers for the same key never construct two tallies.
        """
        with self._lock:
            guarded = self._memo.get(key)
            if guarded is None:
                guarded = _GuardedTally(build())
                self._memo.put(key, guarded)
            return guarded

    def forget(self, run_dir: Path) -> None:
        """Drop every memoized tally for evidence files under *run_dir*.

        Called once a run is terminal: nothing more will be appended to its
        evidence, so its dedup sets are dead weight until other keys evict
        them.
        """
        with self._lock:
            for key in self._memo.keys():
                # Compared as paths, never as a "/"-prefixed string: a key is
                # str(dimension_evidence_file(...)) and carries the platform's
                # separator, so a hardcoded slash evicts nothing on Windows.
                # with_segments parses the key in run_dir's own flavour.
                if run_dir.with_segments(key[0]).is_relative_to(run_dir):
                    self._memo.discard(key)

    def clear(self) -> None:
        """Drop every memoized tally."""
        with self._lock:
            self._memo.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._memo)
