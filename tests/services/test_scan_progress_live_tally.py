"""Live-progress polling reuses one IncrementalTally per evidence file.

Findings 5531/5532: `_dim_evidence_tally` and `_consolidated_dim_progress`
called `tally_unique_findings` from byte 0 on every poll, so a growing
evidence.jsonl got fully re-parsed on every ~2s tick while a pool ran.
`live_tally` memoizes an `IncrementalTally` per (file, suppression state) so
a poll only reads what was appended since the previous one.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from quodeq.data.fs.evidence_tally import FindingTally, tally_unique_findings
from quodeq.services._scan_progress_dims import (
    _LIVE_TALLIES,
    _dim_evidence_tally,
    _standards_stamp,
    _suppression_stamp,
    forget_live_tallies,
    live_tally,
)
from quodeq.services.scan_progress import build_scan_progress


def _row(p, file, line, t="violation"):
    return json.dumps({"p": p, "file": file, "line": line, "t": t}) + "\n"


def _seed_evidence(run_dir: Path, dim_id: str) -> Path:
    path = run_dir / "evidence" / f"{dim_id}_evidence.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_row("P1", "a.py", 1) + _row("P2", "b.py", 2))
    return path


def _memo_key(path, dim_id, dismissed, deleted, evaluators_dir, compiled_dir):
    return (str(path), (dim_id, _suppression_stamp(dismissed, deleted),
                        _standards_stamp(evaluators_dir), _standards_stamp(compiled_dir)))


def test_dim_progress_polls_reuse_one_incremental_tally_per_file(tmp_path):
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "no_such_evaluators"
    compiled_dir = tmp_path / "no_such_compiled"
    path = _seed_evidence(run_dir, dim_id)
    dismissed, deleted = frozenset(), frozenset()

    first = _dim_evidence_tally(dim_id, run_dir, dismissed, deleted, evaluators_dir, compiled_dir)
    assert first == tally_unique_findings(path)

    with path.open("a") as f:
        f.write(_row("P3", "c.py", 3))

    second = _dim_evidence_tally(dim_id, run_dir, dismissed, deleted, evaluators_dir, compiled_dir)
    assert second == tally_unique_findings(path)

    assert len(_LIVE_TALLIES) == 1
    key = _memo_key(path, dim_id, dismissed, deleted, evaluators_dir, compiled_dir)
    guarded = _LIVE_TALLIES.get(key)
    assert guarded is not None
    assert guarded.tally.offset == path.stat().st_size


def test_a_changed_suppression_state_starts_a_fresh_tally(tmp_path):
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "no_such_evaluators"
    compiled_dir = tmp_path / "no_such_compiled"
    _seed_evidence(run_dir, dim_id)

    _dim_evidence_tally(dim_id, run_dir, frozenset(), frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 1

    changed = frozenset({("security", "a.py", 1)})
    _dim_evidence_tally(dim_id, run_dir, changed, frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 2


def test_an_unhashable_suppression_state_is_never_memoized(tmp_path):
    """Finding 4: a plain set has no usable memo key. Keying on id() lets a
    later, different object land on a freed id and resume a tally built with
    the previous predicate, so such a poll stores nothing at all."""
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "no_such_evaluators"
    compiled_dir = tmp_path / "no_such_compiled"
    path = _seed_evidence(run_dir, dim_id)

    first = _dim_evidence_tally(
        dim_id, run_dir, {("security", "a.py", 1)}, set(), evaluators_dir, compiled_dir)
    second = _dim_evidence_tally(
        dim_id, run_dir, {("security", "b.py", 2)}, set(), evaluators_dir, compiled_dir)

    assert len(_LIVE_TALLIES) == 0
    assert first == second == tally_unique_findings(path)


def test_a_new_standard_on_disk_starts_a_fresh_tally(tmp_path):
    """Finding 13: the principle resolver is built from the standards dirs, so
    a standard imported mid-run must not keep resuming the old tally."""
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    dim_id = "security"
    evaluators_dir = tmp_path / "evaluators"
    evaluators_dir.mkdir()
    compiled_dir = tmp_path / "no_such_compiled"
    _seed_evidence(run_dir, dim_id)

    _dim_evidence_tally(dim_id, run_dir, frozenset(), frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 1

    before = evaluators_dir.stat().st_mtime_ns
    (evaluators_dir / "custom.json").write_text("{}")
    assert evaluators_dir.stat().st_mtime_ns != before, "dir mtime did not move"

    _dim_evidence_tally(dim_id, run_dir, frozenset(), frozenset(), evaluators_dir, compiled_dir)
    assert len(_LIVE_TALLIES) == 2


def test_one_run_s_advance_does_not_block_another_run_s_poll(tmp_path):
    """Finding 8: the process-wide lock guards the memo, not the file read, so
    a slow advance() on one run cannot serialise every other run's poll."""
    _LIVE_TALLIES.clear()
    gate = threading.Event()

    class _BlockingTally:
        def __init__(self, path, *, suppressed=None, resolver=None):
            self.path = path
            self.offset = 0

        def advance(self):
            if "blocked" in str(self.path):
                assert gate.wait(timeout=5), "advance() was never released"
            return FindingTally()

    import quodeq.services._scan_progress_dims as dims

    original = dims.IncrementalTally
    dims.IncrementalTally = _BlockingTally
    try:
        slow = threading.Thread(target=lambda: live_tally(
            tmp_path / "blocked.jsonl", suppressed=None, resolver=None, memo_key=("a",)))
        slow.start()
        done = threading.Event()

        def _other_poll():
            live_tally(tmp_path / "other.jsonl", suppressed=None, resolver=None, memo_key=("b",))
            done.set()

        other = threading.Thread(target=_other_poll)
        other.start()
        assert done.wait(timeout=2), "a second run's poll waited on the first run's read"
    finally:
        gate.set()
        slow.join(timeout=5)
        other.join(timeout=5)
        dims.IncrementalTally = original


def _write_status(run_dir: Path, state: str) -> None:
    (run_dir / "status.json").write_text(json.dumps({
        "state": state, "phase": "analyzing",
        "started_at": "2026-05-23T08:00:00+00:00", "dimensions": ["security"],
    }), encoding="utf-8")


def test_a_terminal_poll_forgets_the_run_s_tallies(tmp_path):
    """Finding 9: a finished run's dedup sets are dead weight, and waiting for
    256 other keys to evict them keeps every one of them resident."""
    _LIVE_TALLIES.clear()
    project = tmp_path / "proj"
    run = project / "run"
    run.mkdir(parents=True)
    _seed_evidence(run, "security")

    _write_status(run, "running")
    assert build_scan_progress("job-1", run) is not None
    assert len(_LIVE_TALLIES) == 1

    _write_status(run, "done")
    assert build_scan_progress("job-1", run) is not None
    assert len(_LIVE_TALLIES) == 0


def test_forget_live_tallies_drops_only_the_given_run(tmp_path):
    _LIVE_TALLIES.clear()
    kept = tmp_path / "other-run"
    dropped = tmp_path / "run"
    for run_dir in (kept, dropped):
        _seed_evidence(run_dir, "security")
        _dim_evidence_tally("security", run_dir, frozenset(), frozenset(), None, None)
    assert len(_LIVE_TALLIES) == 2

    forget_live_tallies(dropped)

    assert len(_LIVE_TALLIES) == 1
