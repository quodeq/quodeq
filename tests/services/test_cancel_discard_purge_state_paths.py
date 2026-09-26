"""Discard scratch-file cleanup and path-safety guards.

Split from test_cancel_discard_purge_state.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services.evaluation_mixin import discard_run_state


def test_discard_removes_the_replayed_keys_sidecar(tmp_path: Path):
    """Every per-dim scratch file must go, or the status-GET scoring path can
    resurrect state from leftovers."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    sidecar = evidence / "security_replayed_unconsolidated_keys.json"
    sidecar.write_text(json.dumps({"a.py": "key-a"}))

    discard_run_state(str(reports), {"outputProject": "proj", "outputRunId": "run1"})

    assert not sidecar.exists()


def test_discard_does_not_delete_replayed_cache_entries(tmp_path: Path):
    """The replayed entries were written by an EARLIER run. Discard wipes only
    what this run created; deleting these would destroy a prior kept run's
    cached work."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"b.py": "key-mine"})
    )
    (evidence / "security_replayed_unconsolidated_keys.json").write_text(
        json.dumps({"a.py": "key-theirs"})
    )

    deleted: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            deleted.append(key)

    discard_run_state(
        str(reports), {"outputProject": "proj", "outputRunId": "run1"}, cache=_FakeCache(),
    )

    assert deleted == ["key-mine"]


def test_discard_rejects_path_traversal_in_run_id(tmp_path: Path):
    """Path traversal in run_id must not reach cache-key lookup or file deletion.

    A malicious run_id like "../../../etc/passwd" must be rejected before
    it can cause damage, even if reports_dir and project are legitimate.
    """
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"a.py": "key-should-not-delete"})
    )

    deleted: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            deleted.append(key)

    discard_run_state(
        str(reports),
        {"outputProject": "proj", "outputRunId": "../../../etc/passwd"},
        cache=_FakeCache(),
    )

    assert deleted == [], "traversal run_id must not trigger cache deletion"
    assert (evidence / "security_dispatch_keys.json").exists(), (
        "traversal run_id must not delete files"
    )


def test_discard_rejects_absolute_path_in_project(tmp_path: Path):
    """Absolute paths in project name must not reach cache-key lookup.

    An absolute-path-shaped project value must be rejected before use.
    """
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"a.py": "key-should-not-delete"})
    )

    deleted: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            deleted.append(key)

    discard_run_state(
        str(reports),
        {"outputProject": "/etc", "outputRunId": "run1"},
        cache=_FakeCache(),
    )

    assert deleted == [], "absolute-path project must not trigger cache deletion"
    assert (evidence / "security_dispatch_keys.json").exists(), (
        "absolute-path project must not delete files"
    )


def test_discard_allows_legitimate_paths(tmp_path: Path):
    """Normal legitimate project/run_id values work unchanged."""
    reports = tmp_path / "reports"
    evidence = reports / "myproj" / "run-123" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"a.py": "key-to-delete"})
    )
    (evidence / "security_evidence.jsonl").write_text('{"file":"a.py"}\n')

    deleted: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            deleted.append(key)

    discard_run_state(
        str(reports),
        {"outputProject": "myproj", "outputRunId": "run-123"},
        cache=_FakeCache(),
    )

    assert deleted == ["key-to-delete"], "legitimate paths must work normally"
    assert not (evidence / "security_evidence.jsonl").exists(), (
        "legitimate paths must delete evidence"
    )


def test_discard_logs_and_continues_past_an_invalid_sidecar_key(tmp_path: Path):
    """A ValueError from one key's cache.delete (invalid sidecar key) is
    logged, and the remaining keys still get deleted."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"a.py": "bad-key", "b.py": "good-key"})
    )

    deleted: list[str] = []
    warnings: list[str] = []

    class _FakeCache:
        def delete(self, key: str) -> None:
            if key == "bad-key":
                raise ValueError("malformed key")
            deleted.append(key)

    class _FakeLog:
        def warning(self, message: str) -> None:
            warnings.append(message)

    discard_run_state(
        str(reports), {"outputProject": "proj", "outputRunId": "run1"},
        cache=_FakeCache(), log=_FakeLog(),
    )

    assert deleted == ["good-key"], "the loop must keep going after one bad key"
    assert any("bad-key" in w for w in warnings)


def test_discard_unnamed_cache_delete_exception_propagates(tmp_path: Path):
    """A RuntimeError from cache.delete is outside the (ValueError,) tuple: it
    signals a real bug in the cache backend, not a malformed key, and must
    propagate rather than be silently swallowed."""
    reports = tmp_path / "reports"
    evidence = reports / "proj" / "run1" / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "security_dispatch_keys.json").write_text(
        json.dumps({"a.py": "key-a"})
    )

    class _FakeCache:
        def delete(self, key: str) -> None:
            raise RuntimeError("cache backend is broken")

    with pytest.raises(RuntimeError, match="cache backend is broken"):
        discard_run_state(
            str(reports), {"outputProject": "proj", "outputRunId": "run1"},
            cache=_FakeCache(),
        )
