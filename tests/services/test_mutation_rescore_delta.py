"""Tests for ``dismiss_delta`` — the dismiss mutation-delta envelope.

The dismiss endpoint returns a ``delta`` alongside the slim ``scores`` so the
client can patch its React Query caches synchronously. ``isLatest`` MUST match
the Overview's own latest-run resolution (``_resolve_selected_run("latest")``,
which picks the first ``complete`` run in newest-first ``list_runs`` order).
"""
import os
from pathlib import Path

from quodeq.services.mutation_rescore import (
    delete_all_delta,
    delete_delta,
    dismiss_delta,
    restore_all_delta,
    restore_delta,
)

_DISMISSED = {"req": "R1", "file": "a.py", "line": 10}
_RESTORED = {"req": "R1", "file": "a.py", "line": 10}
_DELETED = {"dimension": "security", "principle": "Integrity", "file": "a.py"}


def _make_run(root: Path, project: str, run_id: str, *, in_progress: bool = False) -> Path:
    """Create a ``list_runs``-visible run dir under ``root/project/run_id``."""
    run_dir = root / project / run_id
    (run_dir / "evidence").mkdir(parents=True)
    (run_dir / "evidence" / "manifest.json").write_text("{}")
    if in_progress:
        # Own PID passes the liveness check → list_runs marks it in_progress.
        (run_dir / ".pid").write_text(str(os.getpid()))
    return run_dir


class TestDismissDeltaEnvelope:
    def test_envelope_shape_with_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = dismiss_delta(str(tmp_path), "proj", "run-1", dict(_DISMISSED))
        assert delta["kind"] == "dismiss"
        assert delta["runId"] == "run-1"
        assert delta["dismissed"] == {"req": "R1", "file": "a.py", "line": 10}
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_carries_its_own_project(self, tmp_path):
        # The assistant apply handler patches caches keyed on the delta's own
        # project, not the live-selected one, so the delta must name it. This
        # prevents patching project B's cache with project A's rollup when the
        # user switches projects while an apply POST is in flight.
        _make_run(tmp_path, "projA", "run-1")
        delta = dismiss_delta(str(tmp_path), "projA", "run-1", dict(_DISMISSED))
        assert delta["project"] == "projA"

    def test_without_run_id_accumulated_is_none(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = dismiss_delta(str(tmp_path), "proj", None, dict(_DISMISSED))
        assert delta["runId"] is None
        assert delta["accumulated"] is None
        assert delta["dismissed"] == {"req": "R1", "file": "a.py", "line": 10}
        assert delta["isLatest"] is False

    def test_accumulated_present_when_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = dismiss_delta(str(tmp_path), "proj", "run-1", dict(_DISMISSED))
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]
        assert "summary" in delta["accumulated"]


class TestDismissDeltaIsLatest:
    def test_is_latest_true_on_latest_run(self, tmp_path):
        # run-2 sorts newest-first (run_id desc) → it is the latest complete run.
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        delta = dismiss_delta(str(tmp_path), "proj", "run-2", dict(_DISMISSED))
        assert delta["isLatest"] is True

    def test_is_latest_false_on_older_run(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        delta = dismiss_delta(str(tmp_path), "proj", "run-1", dict(_DISMISSED))
        assert delta["isLatest"] is False

    def test_is_latest_resolves_to_last_complete_when_in_progress_exists(self, tmp_path):
        # run-3 is in_progress → excluded from default view; the latest COMPLETE
        # run is run-2. Dismissing on run-2 must read isLatest=True; run-3 False.
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        _make_run(tmp_path, "proj", "run-3", in_progress=True)
        assert dismiss_delta(str(tmp_path), "proj", "run-2", dict(_DISMISSED))["isLatest"] is True
        assert dismiss_delta(str(tmp_path), "proj", "run-3", dict(_DISMISSED))["isLatest"] is False


class TestRestoreDeltaEnvelope:
    def test_envelope_shape_with_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = restore_delta(str(tmp_path), "proj", "run-1", dict(_RESTORED))
        assert delta["kind"] == "restore"
        assert delta["runId"] == "run-1"
        assert delta["restored"] == {"req": "R1", "file": "a.py", "line": 10}
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_accumulated_present_when_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = restore_delta(str(tmp_path), "proj", "run-1", dict(_RESTORED))
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]
        assert "summary" in delta["accumulated"]

    def test_without_run_id_accumulated_is_none(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = restore_delta(str(tmp_path), "proj", None, dict(_RESTORED))
        assert delta["runId"] is None
        assert delta["accumulated"] is None
        assert delta["isLatest"] is False
        assert delta["restored"] == {"req": "R1", "file": "a.py", "line": 10}

    def test_is_latest_true_on_latest_run(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        assert restore_delta(str(tmp_path), "proj", "run-2", dict(_RESTORED))["isLatest"] is True
        assert restore_delta(str(tmp_path), "proj", "run-1", dict(_RESTORED))["isLatest"] is False


class TestDeleteDeltaEnvelope:
    def test_envelope_shape_with_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = delete_delta(str(tmp_path), "proj", "run-1", dict(_DELETED))
        assert delta["kind"] == "delete"
        assert delta["runId"] == "run-1"
        assert delta["deleted"] == {
            "dimension": "security", "principle": "Integrity", "file": "a.py",
        }
        assert "isLatest" in delta
        assert "accumulated" in delta

    def test_accumulated_present_when_run_id(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = delete_delta(str(tmp_path), "proj", "run-1", dict(_DELETED))
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]
        assert "summary" in delta["accumulated"]

    def test_without_run_id_accumulated_is_none(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = delete_delta(str(tmp_path), "proj", None, dict(_DELETED))
        assert delta["runId"] is None
        assert delta["accumulated"] is None
        assert delta["isLatest"] is False
        assert delta["deleted"] == {
            "dimension": "security", "principle": "Integrity", "file": "a.py",
        }

    def test_is_latest_true_on_latest_run(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        assert delete_delta(str(tmp_path), "proj", "run-2", dict(_DELETED))["isLatest"] is True
        assert delete_delta(str(tmp_path), "proj", "run-1", dict(_DELETED))["isLatest"] is False


class TestBulkDeltaEnvelopes:
    """restore_all / delete_all carry no single finding — just kind/run/isLatest/accumulated."""

    def test_restore_all_envelope_shape(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = restore_all_delta(str(tmp_path), "proj", "run-1")
        assert delta["kind"] == "restore_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]
        assert "restored" not in delta
        assert "deleted" not in delta

    def test_delete_all_envelope_shape(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        delta = delete_all_delta(str(tmp_path), "proj", "run-1")
        assert delta["kind"] == "delete_all"
        assert delta["runId"] == "run-1"
        assert "isLatest" in delta
        assert delta["accumulated"] is not None
        assert "dimensions" in delta["accumulated"]

    def test_bulk_without_run_id_accumulated_is_none(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        r = restore_all_delta(str(tmp_path), "proj", None)
        d = delete_all_delta(str(tmp_path), "proj", None)
        assert r["runId"] is None and r["accumulated"] is None and r["isLatest"] is False
        assert d["runId"] is None and d["accumulated"] is None and d["isLatest"] is False

    def test_bulk_is_latest_true_on_latest_run(self, tmp_path):
        _make_run(tmp_path, "proj", "run-1")
        _make_run(tmp_path, "proj", "run-2")
        assert restore_all_delta(str(tmp_path), "proj", "run-2")["isLatest"] is True
        assert delete_all_delta(str(tmp_path), "proj", "run-1")["isLatest"] is False
