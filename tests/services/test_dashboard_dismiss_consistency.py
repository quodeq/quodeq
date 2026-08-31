import json
from pathlib import Path
import pytest

from quodeq.analysis._report_io import write_dimension_report
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.services._dashboard_cache import _shared_dimension_cache
from quodeq.services.dashboard import build_dashboard, clear_shared_dimension_cache
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.evidence_rescore import score_dimension_from_evidence
from quodeq.services.score_cache import score_cache_version
from quodeq.core.scoring.params import DEFAULT_PARAMS
from tests.services._scalar_fixtures import build_projected_run


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    clear_shared_dimension_cache()
    yield
    clear_shared_dimension_cache()


def _versions_in_shared_cache() -> set:
    """Return the suppression-version component of every 4-tuple shared-cache key."""
    return {k[3] for k in _shared_dimension_cache.keys() if len(k) == 4}


def test_dismiss_produces_a_new_shared_cache_version(tmp_path):
    """After a dismiss, the shared in-memory dim cache is keyed by the project's
    suppression version, so no read path can serve a pre-dismiss entry.

    A dismiss activates the trend fetcher's *heavy* (rescoring) path, which is
    the one that populates the shared dimension cache. Before the fix its keys
    were 3-tuples with no version component, so ``_versions_in_shared_cache()``
    was empty and this assertion failed. After the fix the key carries the
    suppression hash from ``score_cache_version``.
    """
    reports = tmp_path / "evaluations"
    project = "proj"
    build_projected_run(reports, project, "20260101T000000", {"security": (7.0, "Fair")})

    # Warm on a clean project so nothing but a dismiss can introduce a version.
    build_dashboard(reports, project, run="latest")
    versions_before = _versions_in_shared_cache()

    # ``dismiss_finding(project_dir, finding: dict)`` -- confirmed against
    # src/quodeq/services/dismissed.py; the dict keys are req/file/line.
    dismiss_finding(reports / project, {"req": "R1", "file": "a.py", "line": 1})
    assert dismissed_keys(reports / project), "dismiss did not register"

    build_dashboard(reports, project, run="latest")
    versions_after = _versions_in_shared_cache()

    # A new suppression version key appeared -> the pre-dismiss entry is no longer
    # the one served. Before the fix, keys were 3-tuples with no version, so
    # `_versions_in_shared_cache()` would be empty and this assertion would fail.
    new_versions = versions_after - versions_before
    assert new_versions, "dismiss did not produce a new shared-cache version key"

    # The new key is versioned by the project's actual suppression state.
    expected = score_cache_version(reports / project, DEFAULT_PARAMS)
    assert expected in new_versions, (
        "shared-cache version does not match the project suppression hash"
    )


def _ev_line(dim, req, file, line, sev="major", t="violation", p="Modularity", vt="VT-COUPLING"):
    """One evidence-jsonl judgment (same shape as tests/services/test_evidence_rescore.py)."""
    return {"schema_version": 1, "req": req, "t": t, "file": file, "line": line,
            "severity": sev, "w": "title", "reason": f"reason {req} {file} {line}",
            "vt": vt, "p": p, "d": dim}


def test_dismissed_dimension_score_comes_from_run_evidence(tmp_path):
    """After a dismiss, the dashboard serves the evidence-based rescore.

    The run's report JSON is generated from its own evidence jsonl via the
    real pipeline (``score_evidence`` + ``write_dimension_report``), so the
    stored score and the evidence score agree by construction. Dismissing one
    finding must then re-score the dimension from that run's evidence (the
    exact scan-time basis) -- NOT via the legacy report-JSON formula, which
    loses violation types and diverges. Requires ``build_dashboard`` to pass
    ``run_dir`` down to ``_rescore_dimension``.
    """
    reports = tmp_path / "evaluations"
    project = "proj"
    run_id = "20260101T000000"
    run_dir = reports / project / run_id
    dim = "maintainability"
    sfc, files_read = 10, 5

    # Evidence: typed violations (two sharing a violation_type) so the
    # taxonomy-mode evidence score differs from the reason-fallback legacy
    # formula once a finding is dismissed.
    lines = [
        _ev_line(dim, "R-1", "a.kt", 10, sev="major", vt="VT-COUPLING"),
        _ev_line(dim, "R-2", "a.kt", 20, sev="critical", vt="VT-GODCLASS"),
        _ev_line(dim, "R-5", "b.kt", 7, sev="major", vt="VT-COUPLING"),
        _ev_line(dim, "C-1", "a.kt", 1, t="compliance"),
        _ev_line(dim, "C-3", "b.kt", 3, t="compliance"),
        _ev_line(dim, "R-4", "c.kt", 9, sev="major", vt="VT-DUPLICATION", p="Reusability"),
        _ev_line(dim, "C-2", "c.kt", 2, t="compliance", p="Reusability"),
    ]
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True)
    jsonl = ev_dir / f"{dim}_evidence.jsonl"
    jsonl.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")
    # list_runs only recognizes a run dir that has evidence/manifest.json.
    (ev_dir / "manifest.json").write_text(
        json.dumps({"language_stats": {}, "source_files_count": sfc}),
        encoding="utf-8")
    # read_run_data (no evaluation.db here) sources each dimension's
    # sourceFileCount from <dim>_evidence.json -- the rescore needs it to
    # match the scan-time confidence classification.
    (ev_dir / f"{dim}_evidence.json").write_text(
        json.dumps({"source_file_count": sfc, "date": "2026-01-01"}),
        encoding="utf-8")

    evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
        language=dim, repository=project, date_str="2026-01-01",
        source_file_count=sfc, files_read=files_read,
    ))
    scores = score_evidence(evidence, mode="numerical", params=DEFAULT_PARAMS)
    write_dimension_report(evidence, scores, dim, run_dir / "evaluation")
    (run_dir / "status.json").write_text(
        json.dumps({"state": "complete"}), encoding="utf-8")

    dismiss_finding(reports / project, {"req": "R-2", "file": "a.kt", "line": 20})
    dismissed = dismissed_keys(reports / project)
    assert dismissed, "dismiss did not register"

    expected = score_dimension_from_evidence(
        run_dir, dim, dismissed=dismissed, deleted=set(),
        source_file_count=sfc, files_read=files_read, params=DEFAULT_PARAMS,
    )
    assert expected is not None
    assert expected.overall.weighted_score is not None

    payload = build_dashboard(reports, project, run="latest", params=DEFAULT_PARAMS)
    served = next(d for d in payload["dimensions"] if d["dimension"] == dim)
    # The dismissed violation is gone from the served list...
    assert "R-2" not in {v.get("req") for v in served["violations"]}
    # ...and the served score is the evidence-basis rescore.
    assert served["overallScore"] == f"{expected.overall.weighted_score}/10"
