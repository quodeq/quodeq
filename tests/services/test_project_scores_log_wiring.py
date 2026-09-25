"""``get_project_scores`` threads a real sink into ``compute_accumulated``.

Every function on that path (``compute_accumulated`` down through
``_read_run_data_safely``) defaults its ``log`` parameter to ``NULL_LOG``, so
a best-effort per-run read failure during the accumulated walk was silently
invisible unless a caller opted in. ``scoring/_project_scores.py`` is that
opt-in: it already imports ``SHARED_LOG`` for ``cached_accumulated`` (see
``services/_score_cache_fetch.py``), so it is the nearest caller with a real
sink in scope for ``compute_accumulated`` too.

Driven through the public ``get_project_scores`` entry point (not the
private ``_project_scores``/``_ScoresRequest`` it's built from), taking the
cache-bypass branch (a project with children skips the score cache
entirely -- see ``_resolve_accumulated``) so ``compute_accumulated`` is
reached directly and deterministically.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.shared.log_sink import SHARED_LOG


def _write_json(path: Path, payload: dict) -> None:
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_get_project_scores_threads_shared_log_into_compute_accumulated(tmp_path, monkeypatch):
    from quodeq.services.scoring import get_project_scores

    reports_root = tmp_path / "reports"
    run_dir = reports_root / "proj" / "20260101"
    _write_json(run_dir / "evidence" / "manifest.json", {})
    (run_dir / "scan.json").write_text("{}")

    # Take the cache-bypass branch (_resolve_accumulated: a project with
    # children never hits the score cache), so compute_accumulated is
    # called directly and deterministically.
    monkeypatch.setattr(
        "quodeq.services.scoring._project_scores.find_children",
        lambda *_a, **_kw: ["child"],
    )

    calls: list[object] = []

    def _spy(reports_dir, project, as_of, *, params=None, log=None):
        calls.append(log)
        return {"dimensions": [], "summary": {}}

    monkeypatch.setattr("quodeq.services.scoring._project_scores.compute_accumulated", _spy)

    result = get_project_scores(reports_root, "proj")

    assert result is not None
    # Identity, not just equality: proves the exact production SHARED_LOG
    # singleton reached compute_accumulated, not a copy or shim.
    assert calls == [SHARED_LOG]
    assert calls[0] is SHARED_LOG
