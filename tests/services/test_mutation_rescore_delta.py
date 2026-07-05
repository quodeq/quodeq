"""Tests for ``dismiss_delta`` — the dismiss mutation-delta envelope.

The dismiss endpoint returns a ``delta`` alongside the slim ``scores`` so the
client can patch its React Query caches synchronously. ``isLatest`` MUST match
the Overview's own latest-run resolution (``_resolve_selected_run("latest")``,
which picks the first ``complete`` run in newest-first ``list_runs`` order).
"""
import os
from pathlib import Path

from quodeq.services.mutation_rescore import dismiss_delta

_DISMISSED = {"req": "R1", "file": "a.py", "line": 10}


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
