"""Live-progress polling reuses one IncrementalTally per evidence file.

`_dim_evidence_tally` and `consolidated_dim_progress`
called `tally_unique_findings` from byte 0 on every poll, so a growing
evidence.jsonl got fully re-parsed on every ~2s tick while a pool ran.
`live_tally` memoizes an `IncrementalTally` per (file, suppression state) so
a poll only reads what was appended since the previous one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath

from quodeq.data.fs.evidence_tally import tally_unique_findings
from quodeq.data.fs.run_files import dimension_evidence_file
from quodeq.services._scan_progress_dims import (
    _LIVE_TALLIES,
    _dim_evidence_tally,
    _standards_stamp,
    _suppression_stamp,
    forget_live_tallies,
    live_tally,
)
from quodeq.services._scan_progress_types import ProgressContext
from quodeq.services.scan_progress import build_scan_progress


def _ctx(run_dir: Path, evaluators_dir=None, compiled_dir=None) -> ProgressContext:
    """The run-level context `_dim_evidence_tally` reads.

    It only touches `run_dir`, `evaluators_dir` and `compiled_dir`; the rest
    are filled with inert values. These used to be separate positional args
    and were bundled into `ProgressContext` by the parameter-count ratchet.
    """
    return ProgressContext(
        run_dir=run_dir, status={}, state="running", is_terminal=False,
        total_elapsed_s=None, run_budget_s=None, project_files=0,
        dim_estimates={}, dim_records={}, dim_ids=[],
        evidence_dir=run_dir / "evidence",
        evaluators_dir=evaluators_dir, compiled_dir=compiled_dir,
    )


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
    ctx = _ctx(run_dir, evaluators_dir, compiled_dir)

    first = _dim_evidence_tally(dim_id, ctx, dismissed, deleted)
    assert first == tally_unique_findings(path)

    with path.open("a") as f:
        f.write(_row("P3", "c.py", 3))

    second = _dim_evidence_tally(dim_id, ctx, dismissed, deleted)
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
    ctx = _ctx(run_dir, evaluators_dir, compiled_dir)

    _dim_evidence_tally(dim_id, ctx, frozenset(), frozenset())
    assert len(_LIVE_TALLIES) == 1

    changed = frozenset({("security", "a.py", 1)})
    _dim_evidence_tally(dim_id, ctx, changed, frozenset())
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

    ctx = _ctx(run_dir, evaluators_dir, compiled_dir)
    first = _dim_evidence_tally(dim_id, ctx, {("security", "a.py", 1)}, set())
    second = _dim_evidence_tally(dim_id, ctx, {("security", "b.py", 2)}, set())

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

    _dim_evidence_tally(dim_id, _ctx(run_dir, evaluators_dir, compiled_dir),
                        frozenset(), frozenset())
    assert len(_LIVE_TALLIES) == 1

    before = evaluators_dir.stat().st_mtime_ns
    (evaluators_dir / "custom.json").write_text("{}")
    # Windows directory mtime is coarse enough that a write landing in the same
    # filesystem tick leaves st_mtime_ns untouched, which tripped this
    # precondition before the assertion below it ever ran. What is under test is
    # that a CHANGED standards stamp starts a fresh tally, not how quickly the OS
    # notices the write, so move the stamp ourselves when the write did not.
    if evaluators_dir.stat().st_mtime_ns == before:
        bumped = before + 1_000_000_000
        os.utime(evaluators_dir, ns=(bumped, bumped))
    assert evaluators_dir.stat().st_mtime_ns != before, "dir mtime did not move"

    # A fresh _ctx on purpose: the stamp is re-read from disk, not cached.
    _dim_evidence_tally(dim_id, _ctx(run_dir, evaluators_dir, compiled_dir),
                        frozenset(), frozenset())
    assert len(_LIVE_TALLIES) == 2


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
        _dim_evidence_tally("security", _ctx(run_dir), frozenset(), frozenset())
    assert len(_LIVE_TALLIES) == 2

    forget_live_tallies(dropped)

    assert len(_LIVE_TALLIES) == 1
    surviving = _LIVE_TALLIES.keys()[0][0]
    assert Path(surviving) == dimension_evidence_file(kept, "security")


def test_forget_live_tallies_matches_keys_whatever_the_separator(tmp_path):
    """The memo key is str(dimension_evidence_file(...)), so it carries the
    platform's separator. Matching it against a "/"-joined prefix made the
    eviction a no-op on Windows.

    The native half above goes through _dim_evidence_tally; this one feeds the
    matcher a backslash-separated key with a PureWindowsPath run_dir, which is
    exactly the shape Windows produces, on any platform.
    """
    _LIVE_TALLIES.clear()
    win_run = PureWindowsPath(r"C:\runs\run-1")
    win_key = (str(win_run / "evidence" / "security_evidence.jsonl"), ("security",))
    other_key = (str(PureWindowsPath(r"C:\runs\run-2\evidence\security_evidence.jsonl")),
                 ("security",))
    assert "\\" in win_key[0], "the key under test must be backslash-separated"
    _LIVE_TALLIES.put(win_key, object())
    _LIVE_TALLIES.put(other_key, object())

    forget_live_tallies(win_run)

    assert _LIVE_TALLIES.keys() == [other_key]


def test_a_memo_hit_never_builds_a_resolver(tmp_path):
    _LIVE_TALLIES.clear()
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1))
    built: list[int] = []
    make = lambda: built.append(1)  # noqa: E731 - trivial counter, not worth a def
    live_tally(path, suppressed=None, make_resolver=make, memo_key=("k",))
    live_tally(path, suppressed=None, make_resolver=make, memo_key=("k",))
    assert built == [1]


def test_an_unkeyed_tally_builds_its_resolver_every_call(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text(_row("P1", "a.py", 1))
    built: list[int] = []
    make = lambda: built.append(1)  # noqa: E731 - trivial counter, not worth a def
    live_tally(path, suppressed=None, make_resolver=make, memo_key=None)
    live_tally(path, suppressed=None, make_resolver=make, memo_key=None)
    assert built == [1, 1]


def test_repeat_dim_polls_build_the_resolver_once(tmp_path, monkeypatch):
    _LIVE_TALLIES.clear()
    run_dir = tmp_path / "run"
    _seed_evidence(run_dir, "security")
    ctx = _ctx(run_dir, tmp_path / "no_such_evaluators", tmp_path / "no_such_compiled")
    builds: list[str] = []
    counting = lambda dim_id, *a, **k: builds.append(dim_id)  # noqa: E731
    monkeypatch.setattr(
        "quodeq.services._scan_progress_dims.build_principle_resolver", counting)
    for _ in range(3):
        _dim_evidence_tally("security", ctx, frozenset(), frozenset())
    assert builds == ["security"]
