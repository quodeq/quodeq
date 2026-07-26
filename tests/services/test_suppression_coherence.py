"""One dismiss, one answer: every suppression surface agrees.

Golden test for the unified exclusion predicate. A single dismissed finding
(here the hard case: a finding without a req, dismissed under the UI's
`req || principle` fallback key) must be excluded by:

- the live-counter matcher (services/suppression),
- the evidence-based rescore (services/evidence_rescore),
- the report-level filter (services/rescore),
- the CLI excluded-findings count (_cli_evaluation),
- the CI report/SARIF filter (ci/_suppressions).

If any surface answers differently, counters, grades, CLI output, and CI
exports drift apart for the same project state.
"""
import json
from pathlib import Path

from quodeq.analysis._report_io import write_dimension_report
from quodeq.core.evidence.parser import EvidenceContext, parse_jsonl_to_evidence
from quodeq.core.scoring.engine import score_evidence
from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq._cli_evaluation import _count_excluded_findings
from quodeq.ci._suppressions import filter_suppressed_violations
from quodeq.services.dismissed import dismiss_finding, dismissed_keys
from quodeq.services.evidence_rescore import score_dimension_from_evidence, standard_dirs
from quodeq.services.suppression import matcher_for

DIM = "maintainability"
SFC, FILES_READ = 10, 5


def _build_run(run_dir: Path) -> dict:
    """Real evidence + real scored report through the actual scan pipeline."""
    lines = [
        {"schema_version": 1, "req": "M-MOD-1", "t": "violation", "file": "a.kt",
         "line": 10, "severity": "major", "w": "t", "reason": "r",
         "p": "Modularity", "d": DIM},
        # The hard case: no req. The UI dismisses this under its principle.
        {"schema_version": 1, "t": "violation", "file": "b.kt", "line": 7,
         "severity": "critical", "w": "t", "reason": "r",
         "p": "Modularity", "d": DIM},
        {"schema_version": 1, "req": "M-MOD-2", "t": "compliance", "file": "a.kt",
         "line": 1, "w": "t", "reason": "r", "p": "Modularity", "d": DIM},
    ]
    ev_dir = run_dir / "evidence"
    ev_dir.mkdir(parents=True)
    jsonl = ev_dir / f"{DIM}_evidence.jsonl"
    jsonl.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    compiled_dir, evaluators_dir = standard_dirs()
    evidence = parse_jsonl_to_evidence(jsonl, EvidenceContext(
        language="", repository="", date_str="",
        source_file_count=SFC, files_read=FILES_READ,
    ), compiled_dir=compiled_dir, evaluators_dir=evaluators_dir)
    scores = score_evidence(evidence, mode="numerical", params=DEFAULT_PARAMS)
    write_dimension_report(evidence, scores, DIM, run_dir / "evaluation")
    return json.loads((run_dir / "evaluation" / f"{DIM}.json").read_text())


def test_one_dismiss_every_surface_agrees(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_EVALUATORS_DIR", str(tmp_path / "no-evals"))
    project_dir = tmp_path / "proj"
    run_dir = project_dir / "run-1"
    report = _build_run(run_dir)

    # Dismiss the no-req critical the way the UI does: key = req || principle.
    dismiss_finding(project_dir, {"req": "Modularity", "file": "b.kt", "line": 7})
    dismissed = dismissed_keys(project_dir)
    assert dismissed, "dismiss did not register"

    # 1. Live-counter matcher hides the raw evidence row.
    matcher = matcher_for(project_dir, DIM)
    row = {"t": "violation", "p": "Modularity", "file": "b.kt", "line": 7}
    assert matcher.is_suppressed(row)

    # 2. CLI counts exactly this one finding as excluded.
    assert _count_excluded_findings(run_dir, DIM, dismissed, set()) == 1

    # 3. The evidence rescore drops it from the grade.
    base = score_dimension_from_evidence(
        run_dir, DIM, dismissed=set(), deleted=set(),
        source_file_count=SFC, files_read=FILES_READ, params=DEFAULT_PARAMS)
    out = score_dimension_from_evidence(
        run_dir, DIM, dismissed=dismissed, deleted=set(),
        source_file_count=SFC, files_read=FILES_READ, params=DEFAULT_PARAMS)
    assert out.principles["Modularity"].deductions.critical_type_count \
        == base.principles["Modularity"].deductions.critical_type_count - 1

    # 4. The CI report/SARIF filter drops it from the scored report dict.
    filtered = filter_suppressed_violations(report, project_dir)
    kept_files = [(v.get("file"), v.get("line")) for v in filtered["violations"]]
    assert ("b.kt", 7) not in kept_files
    assert ("a.kt", 10) in kept_files
