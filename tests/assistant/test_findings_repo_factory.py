"""search_findings/finding_keys_in_scope receive their repository via
ToolContext.findings_repo_factory instead of constructing SQLite inline.

Pins the seam ([6]): a fake FindingsRepository drives both call sites, no
evaluation.db needed — and the ``.is_file()`` guard in finding_keys_in_scope
still prevents any repository from being built (and thus a DB from being
created) for a run without one.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.assistant.tools import ToolContext
from quodeq.assistant.tools._read_tools import _search_findings, finding_keys_in_scope
from quodeq.core.types.finding import Finding
from quodeq.data.ports.findings import FindingsRepository
from quodeq.data.sqlite.assistant_repository import AssistantRepository


class FakeFindingsRepo:
    def __init__(self, findings: list[Finding]) -> None:
        self._findings = findings
        self.search_calls: list[dict] = []

    def insert_finding(self, finding: dict) -> bool:
        return True

    def list_by_dimension(self, dimension: str) -> list[Finding]:
        return [f for f in self._findings if f.dimension == dimension]

    def list_all(self) -> list[Finding]:
        return list(self._findings)

    def count_by_dimension(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self._findings:
            out[f.dimension or ""] = out.get(f.dimension or "", 0) + 1
        return out

    def search(self, query: str, limit: int = 100, *,
               exclude_dimensions: list[str] | None = None) -> list[Finding]:
        self.search_calls.append(
            {"query": query, "limit": limit,
             "exclude_dimensions": exclude_dimensions})
        return list(self._findings)[:limit]

    def set_verdict(self, *, practice_id: str, file: str, line: int,
                    verdict: str) -> int:
        return 0


def _finding() -> Finding:
    return Finding(practice_id="P1", verdict="violation", file="src/a.py",
                   line=3, reason="sql injection risk", snippet="cur.execute(q)",
                   severity="major", dimension="security", req="req-1")


def _ctx(tmp_path: Path, factory) -> ToolContext:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    repo = AssistantRepository(tmp_path / "assistant.db")
    repo.create_session(session_id="s1", provider="ollama")
    return ToolContext(
        repository=repo, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled",
        dimensions_file=tmp_path / "dimensions.json",
        findings_repo_factory=factory,
    )


def test_fake_repo_satisfies_protocol():
    assert isinstance(FakeFindingsRepo([]), FindingsRepository)


def test_search_findings_uses_injected_factory(tmp_path):
    fake = FakeFindingsRepo([_finding()])
    seen: list[Path] = []

    def factory(run_dir: Path) -> FindingsRepository:
        seen.append(run_dir)
        return fake

    ctx = _ctx(tmp_path, factory)
    out = _search_findings(ctx, "sql", limit=5)

    assert seen == [ctx.run_dir]
    assert fake.search_calls == [
        {"query": "sql", "limit": 5, "exclude_dimensions": None}]
    assert out["findings"][0]["requirement"] == "req-1"
    assert out["findings"][0]["file"] == "src/a.py"
    # No SQLite file was ever created by the tool call.
    assert not (ctx.run_dir / "evaluation.db").exists()


def test_finding_keys_in_scope_uses_injected_factory(tmp_path):
    fake = FakeFindingsRepo([_finding()])
    ctx = _ctx(tmp_path, lambda run_dir: fake)
    # The SQL branch reads only an EXISTING db file.
    (ctx.run_dir / "evaluation.db").touch()

    keys = finding_keys_in_scope(ctx)

    assert ("req-1", "src/a.py", 3) in keys


def test_finding_keys_in_scope_guard_skips_factory_without_db(tmp_path):
    def factory(run_dir: Path) -> FindingsRepository:
        raise AssertionError("factory must not run when evaluation.db is absent")

    ctx = _ctx(tmp_path, factory)

    assert finding_keys_in_scope(ctx) == set()
    assert not (ctx.run_dir / "evaluation.db").exists()
