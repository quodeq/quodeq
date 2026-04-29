import io
from pathlib import Path

from quodeq.analysis.mcp.router import FindingsRouter
from quodeq.data.sqlite.findings_repository import SqliteFindingsRepository


def _args(p="P1", file="x.py", line=1, t="violation"):
    return {"p": p, "file": file, "line": line, "t": t,
            "severity": "medium", "d": "dim", "reason": "r",
            "snippet": "s", "w": "title"}


def test_router_writes_jsonl_and_sqlite(tmp_path: Path):
    fh = io.StringIO()
    repo = SqliteFindingsRepository(tmp_path)
    router = FindingsRouter(fh, findings_repo=repo)

    msg, dup = router.receive(_args())
    assert dup is False
    assert "Finding #1 recorded." in msg

    # JSONL still written
    assert fh.getvalue().count("\n") == 1
    # SQLite has the row too
    assert repo.count_by_dimension() == {"dim": 1}


def test_router_without_repo_only_writes_jsonl(tmp_path: Path):
    fh = io.StringIO()
    router = FindingsRouter(fh)
    msg, dup = router.receive(_args())
    assert dup is False
    assert fh.getvalue().count("\n") == 1


def test_router_dedup_skips_both_writes(tmp_path: Path):
    fh = io.StringIO()
    repo = SqliteFindingsRepository(tmp_path)
    router = FindingsRouter(fh, findings_repo=repo)

    router.receive(_args())
    msg, dup = router.receive(_args())
    assert dup is True
    assert fh.getvalue().count("\n") == 1
    assert repo.count_by_dimension() == {"dim": 1}
