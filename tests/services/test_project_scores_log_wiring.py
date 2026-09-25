"""``get_project_scores`` threads a real sink into ``compute_accumulated``.

Every function on that path (``compute_accumulated`` down through
``_read_run_data_safely``) defaults its ``log`` parameter to ``NULL_LOG``, so
a best-effort per-run read failure during the accumulated walk was silently
invisible unless a caller opted in. ``scoring/_project_scores.py`` is that
opt-in: it already imports ``SHARED_LOG`` for ``cached_accumulated`` (see
``services/_score_cache_fetch.py``), so it is the nearest caller with a real
sink in scope for ``compute_accumulated`` too.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.scoring import NO_DEPS, _project_scores
from quodeq.services.scoring._project_scores import _ScoresRequest
from quodeq.shared.log_sink import SHARED_LOG


def test_compute_accumulated_payload_threads_shared_log(monkeypatch):
    calls: list[object] = []

    def _spy(reports_dir, project, as_of, *, params=None, log=None):
        calls.append(log)
        return {"dimensions": [], "summary": {}}

    monkeypatch.setattr(_project_scores, "compute_accumulated", _spy)
    req = _ScoresRequest(
        reports_root=Path("/tmp/reports"), project="p", as_of=None,
        params=DEFAULT_PARAMS, deps=NO_DEPS,
    )

    _project_scores._compute_accumulated_payload(req, [False])

    assert calls == [SHARED_LOG]


def test_project_scores_imports_the_real_shared_log_singleton():
    # Sanity check that _project_scores.SHARED_LOG is the actual production
    # sink (not a copy/shim) absent any monkeypatching.
    assert _project_scores.SHARED_LOG is SHARED_LOG
