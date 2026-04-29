"""Verify the MCP findings server wires SqliteFindingsRepository into FindingsRouter."""
import io
from pathlib import Path

from quodeq.analysis.mcp.findings_server import _build_router
from quodeq.analysis.mcp.router import CompiledContext
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def test_build_router_wires_sqlite_repo_with_run_dir(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    findings_fh = io.StringIO()
    ctx = CompiledContext()

    router = _build_router(findings_fh, findings_path, ctx)

    assert router._findings_repo is not None
    assert isinstance(router._findings_repo, SqliteFindingsRepository)
    # run_dir should be the grandparent of the findings file
    assert router._findings_repo._run_dir == tmp_path / "run-1"


def test_build_router_emits_findings_to_both_jsonl_and_sqlite(tmp_path: Path):
    findings_path = tmp_path / "run-1" / "evidence" / "timeliness_evidence.jsonl"
    findings_path.parent.mkdir(parents=True)
    fh = io.StringIO()
    router = _build_router(fh, findings_path, CompiledContext())

    msg, dup = router.receive({
        "p": "P1", "file": "x.py", "line": 1, "t": "violation",
        "severity": "medium", "d": "dim", "reason": "r", "snippet": "s",
        "w": "title",
    })

    assert dup is False
    assert fh.getvalue().count("\n") == 1
    repo = SqliteFindingsRepository(tmp_path / "run-1")
    assert repo.count_by_dimension() == {"dim": 1}
