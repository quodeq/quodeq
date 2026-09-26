"""live_tally direct-call tests: the tally_factory injection seam, and the
concurrency test that reaches IncrementalTally through a module-attribute
patch. Split from test_scan_progress_live_tally.py to keep that file under
the file-size cap; these tests call ``live_tally`` directly rather than
through the ``_dim_evidence_tally``/``consolidated_dim_progress`` wrappers.
"""
from __future__ import annotations

import threading
from pathlib import Path

from tests._timeouts import budget

from quodeq.data.fs.evidence_tally import FindingTally
from quodeq.services.wiring import LiveTallyMemo
import quodeq.services._scan_progress_dims as dims


def test_one_run_s_advance_does_not_block_another_run_s_poll(tmp_path):
    """Finding 8: the process-wide lock guards the memo, not the file read, so
    a slow advance() on one run cannot serialise every other run's poll."""
    memo = LiveTallyMemo()
    gate = threading.Event()

    class _BlockingTally:
        def __init__(self, path, *, suppressed=None, resolver=None):
            self.path = path
            self.offset = 0

        def advance(self):
            if "blocked" in str(self.path):
                assert gate.wait(timeout=budget(5)), "advance() was never released"
            return FindingTally()

    original = dims.IncrementalTally
    dims.IncrementalTally = _BlockingTally
    try:
        slow = threading.Thread(target=lambda: dims.live_tally(
            tmp_path / "blocked.jsonl", suppressed=None, make_resolver=None, memo_key=("a",), memo=memo))
        slow.start()
        done = threading.Event()

        def _other_poll():
            dims.live_tally(tmp_path / "other.jsonl", suppressed=None, make_resolver=None,
                             memo_key=("b",), memo=memo)
            done.set()

        other = threading.Thread(target=_other_poll)
        other.start()
        assert done.wait(timeout=budget(2)), \
            "a second run's poll waited on the first run's read"
    finally:
        gate.set()
        slow.join(timeout=budget(5))
        other.join(timeout=budget(5))
        dims.IncrementalTally = original


def test_injected_tally_factory_is_used_instead_of_incremental_tally(tmp_path):
    """live_tally's tally_factory seam: a fake factory must back the tally,
    proving the real IncrementalTally class was never constructed."""
    memo = LiveTallyMemo()
    path = tmp_path / "e.jsonl"
    path.write_text('{"p": "P1", "file": "a.py", "line": 1, "t": "violation"}\n')
    built_paths: list[Path] = []

    class _FakeTally:
        def __init__(self, p, *, suppressed=None, resolver=None):
            built_paths.append(p)

        def advance(self):
            return FindingTally(violations=99)

    result = dims.live_tally(
        path, suppressed=None, make_resolver=None, memo_key=("fake-factory",),
        tally_factory=_FakeTally, memo=memo,
    )

    assert built_paths == [path]
    assert result.violations == 99


def test_default_tally_factory_still_resolves_to_the_patched_incremental_tally(tmp_path, monkeypatch):
    """Existing patch target keeps biting: no tally_factory injected -> falls
    back to this module's IncrementalTally, resolved at call time."""
    memo = LiveTallyMemo()
    path = tmp_path / "e.jsonl"
    path.write_text('{"p": "P1", "file": "a.py", "line": 1, "t": "violation"}\n')
    calls: list[Path] = []

    class _SpyTally:
        def __init__(self, p, *, suppressed=None, resolver=None):
            calls.append(p)

        def advance(self):
            return FindingTally()

    monkeypatch.setattr("quodeq.services._scan_progress_dims.IncrementalTally", _SpyTally)
    dims.live_tally(path, suppressed=None, make_resolver=None, memo_key=("spy",), memo=memo)

    assert calls == [path]
