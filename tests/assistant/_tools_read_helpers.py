"""Finding and ToolContext builders shared by the test_tools_read* siblings."""
import json

from quodeq.assistant.tools import ToolContext
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _finding(**over):
    # FindingsRouter wire dict: short keys per finding_dict_to_row
    # (src/quodeq/data/sqlite/_row_mappers.py).
    base = {
        "p": "req-1", "d": "security", "req": "req-1",
        "t": "violation", "severity": "major", "file": "src/a.py",
        "line": 3, "end_line": 3, "w": "t", "reason": "sql injection risk",
        "snippet": "cur.execute(q)", "vt": "code", "context": "",
        "scope": "file", "req_refs": [], "confidence": 90,
        "provenance_downgrade": 0,
    }
    base.update(over)
    return base


def _run_ctx(tmp_path, visible_standard_ids=None, findings=None):
    """A run-scoped ctx with "security" and "reliability" evaluation reports.

    `findings` overrides the SQL findings seeded for search_findings (default:
    a single "security" finding); `visible_standard_ids` plumbs the visibility
    selection through, mirroring `_standards_ctx` in test_tools_read_accumulated.
    """
    run_dir = tmp_path / "run"
    repo_findings = SqliteFindingsRepository(run_dir)
    for f in (findings if findings is not None else [_finding()]):
        repo_findings.insert_finding(f)
    eval_dir = run_dir / "evaluation"
    eval_dir.mkdir(parents=True)
    (eval_dir / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 61.5, "overallGrade": "C",
        "principles": [{"name": "P1", "grade": "C"}],
        "violations": [
            {"principle": "P1", "file": "src/a.py", "line": 3, "severity": "minor",
             "title": "weak thing", "reason": "because", "snippet": "x=1", "context": "ctx"},
            {"principle": "P2", "file": "src/b.py", "line": 7, "severity": "critical",
             "title": "bad thing", "reason": "danger", "snippet": "y=2", "context": "ctx"},
            {"principle": "P1", "file": "src/c.py", "line": 9, "severity": "major",
             "title": "mid thing", "reason": "risky", "snippet": "z=3", "context": "ctx"},
        ],
        "totals": {"violations": 3}, "coveragePct": 80,
    }))
    (eval_dir / "reliability.json").write_text(json.dumps({
        "dimension": "reliability", "overallScore": 70, "overallGrade": "B",
        "principles": [{"name": "R1", "grade": "B"}],
        "violations": [
            {"principle": "R1", "file": "src/r.py", "line": 1, "severity": "major",
             "title": "rel thing", "reason": "flaky", "snippet": "q=4"},
        ],
        "totals": {"violations": 1}, "coveragePct": 90,
    }))
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        visible_standard_ids=visible_standard_ids,
    )


# --- Accumulated (per-dimension-latest) scope: no specific run selected. ------
# The overview picks each dimension's LATEST run independently, so the payload
# spans several runs (fromRunId differs) and keys the principle as "practiceId"
# (serialized Finding) rather than the raw run JSON's "principle".
_ACC = {
    "project": "p",
    "dimensions": [
        {"dimension": "security", "overallScore": "9.6/10", "overallGrade": "Exemplary",
         "fromRunId": "runA", "principles": [{"principle": "S1", "grade": "A"}],
         "totals": {"violations": 2}, "coveragePct": 80,
         "violations": [
             {"practiceId": "S1", "file": "a.kt", "line": 1, "severity": "minor",
              "title": "t1", "reason": "r1", "snippet": "x", "context": "c"},
             {"practiceId": "S2", "file": "b.kt", "line": 2, "severity": "critical",
              "title": "t2", "reason": "r2"},
         ]},
        {"dimension": "reliability", "overallScore": "9.0/10", "overallGrade": "Exemplary",
         "fromRunId": "runB", "principles": [{"principle": "R1", "grade": "A"}],
         "totals": {"violations": 1},
         "violations": [
             {"practiceId": "R1", "file": "r.kt", "line": 3, "severity": "major",
              "title": "t3", "reason": "r3"},
         ]},
    ],
}


def _acc_ctx(tmp_path, monkeypatch, visible_standard_ids=None):
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    monkeypatch.setattr(
        "quodeq.assistant.tools._read_tools._fs_reports.get_accumulated",
        lambda reports_dir, project, as_of: _ACC)
    return ToolContext(
        repository=repo, session_id="s1", run_dir=None, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        project_id="p", reports_dir=tmp_path / "reports",
        visible_standard_ids=visible_standard_ids,
    )
