from datetime import datetime, timezone
from pathlib import Path

import pytest

from quodeq.resolver.models import FindingInput
from quodeq.verifier.models import Verdict
from quodeq.verifier.service import (
    VerifierService,
    LocatedFinding,
    FindingNotFound,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_project(root: Path) -> None:
    _write(
        root / "services" / "base.py",
        """\
from typing import Protocol


class ActionProvider(Protocol):
    \"\"\"Top-level protocol composing all action provider operations.\"\"\"
    ...
""",
    )
    _write(
        root / "services" / "filesystem.py",
        """\
from services.base import ActionProvider


class FilesystemActionProvider(ActionProvider):
    \"\"\"Filesystem-backed implementation of the ActionProvider interface.\"\"\"
    pass
""",
    )
    _write(
        root / "api" / "app.py",
        """\
from services.base import ActionProvider


def _default_provider() -> ActionProvider:
    \"\"\"Create the default filesystem-based provider (lazy import).\"\"\"
    from services.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


def create_app(provider: ActionProvider | None = None):
    provider = provider or _default_provider()
    return provider
""",
    )


def test_service_raises_when_finding_not_found(tmp_path: Path, stub_client):
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=lambda eval_id, dim, fid: None,
        client=stub_client({}),
        model="gemma:4",
    )
    with pytest.raises(FindingNotFound):
        service.verify_finding(
            evaluation_id="eval-1",
            dimension="flexibility",
            finding_id="missing",
        )


def test_service_runs_full_pipeline(tmp_path: Path, stub_client):
    _make_project(tmp_path)

    def locate(eval_id: str, dim: str, fid: str) -> LocatedFinding | None:
        if fid == "f1":
            return LocatedFinding(
                file="api/app.py",
                line=6,
                category="flexibility/adaptability",
                severity="major",
                description="hardcoded provider dependency",
            )
        return None

    response = {
        "checklist": {
            "Q1": {"answer": "yes", "cite": "MANIFEST"},
            "Q2": {"answer": "yes", "cite": "src/api/app.py:6"},
            "Q3": {"answer": "yes", "cite": "MANIFEST"},
            "Q4": {"answer": "yes", "cite": "MANIFEST"},
        },
        "confidence": 0.9,
        "evidence_summary": "ok",
    }

    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=stub_client(response),
        model="gemma:4",
    )
    result = service.verify_finding(
        evaluation_id="eval-1",
        dimension="flexibility",
        finding_id="f1",
    )
    assert result.verdict in (Verdict.FALSE_POSITIVE, Verdict.INCONCLUSIVE)
    assert result.verification_id is not None

    # Verification is persisted in the per-eval store
    store_db = tmp_path / "evals" / "eval-1" / "verifications.db"
    assert store_db.exists()

    # Audit log was written
    log_dir = tmp_path / "evals" / "eval-1" / "verifier" / result.verification_id
    assert (log_dir / "manifest.json").exists()
    assert (log_dir / "response.json").exists()


def test_service_resolves_project_root_per_evaluation(tmp_path: Path, stub_client):
    project_a = tmp_path / "project_a"
    project_b = tmp_path / "project_b"
    _make_project(project_a)
    _make_project(project_b)

    def locate(eval_id: str, dim: str, fid: str) -> LocatedFinding | None:
        return LocatedFinding(
            file="api/app.py", line=6, category="flexibility/adaptability",
            severity="major", description=""
        )

    def project_root_for(eval_id: str) -> Path:
        return {"eval-a": project_a, "eval-b": project_b}.get(eval_id, project_a)

    canned = {
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4")},
        "confidence": 0.5,
        "evidence_summary": "x",
    }
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root_resolver=project_root_for,
        finding_locator=locate,
        client=stub_client(canned, canned),
        model="gemma:4",
    )
    a = service.verify_finding("eval-a", "flexibility", "f1")
    b = service.verify_finding("eval-b", "flexibility", "f1")
    assert a.verification_id != b.verification_id


def test_service_runs_full_pipeline_on_hardcoded_finding(tmp_path: Path, stub_client):
    """v8 has no classifier -- even findings whose title contains no
    substitutability language flow through the model. Previously this would
    have been short-circuited to NOT_APPLICABLE."""
    _make_project(tmp_path)

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="api/app.py", line=6,
            category="flexibility/adaptability", severity="minor",
            description="Hardcoded output filename",  # no substitutability keyword
            reason="The output filename is hardcoded.",  # no substitutability keyword
        )

    canned = {
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4")},
        "confidence": 0.7,
        "evidence_summary": "x",
    }
    client = stub_client(canned)
    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=client,
        model="gemma:4",
    )
    result = service.verify_finding("eval-1", "flexibility", "f1")
    # The stub client WAS called -- proof we didn't short-circuit.
    assert len(client.calls) == 1
    assert result.verdict in (Verdict.CONFIRMED, Verdict.FALSE_POSITIVE, Verdict.INCONCLUSIVE)
    assert result.verdict is not Verdict.NOT_APPLICABLE


def test_read_source_context_marks_cited_line(tmp_path: Path):
    """The service-layer helper reads +-N lines around the cite and marks the
    cited line with >>>. Test it in isolation."""
    from quodeq.verifier.service import _read_source_context

    (tmp_path / "f.py").write_text(
        "\n".join(f"line {i}" for i in range(1, 11)),
        encoding="utf-8",
    )
    ctx = _read_source_context(tmp_path / "f.py", line=5, before=2, after=2)
    # Should include lines 3-7, with line 5 marked.
    assert "line 3" in ctx
    assert "line 7" in ctx
    assert "line 8" not in ctx
    assert "line 2" not in ctx
    # The marker '>>>' precedes the cited line.
    cited_row = next(row for row in ctx.splitlines() if "line 5" in row)
    assert cited_row.startswith(">>>")


def test_read_source_context_clips_to_file_bounds(tmp_path: Path):
    """Context near start/end of file is clipped, not padded with blanks."""
    from quodeq.verifier.service import _read_source_context

    (tmp_path / "g.py").write_text("a\nb\nc\n", encoding="utf-8")
    ctx = _read_source_context(tmp_path / "g.py", line=1, before=30, after=30)
    # 3-line file, +-30 window -> returns all 3 lines.
    assert "a" in ctx and "b" in ctx and "c" in ctx


def test_service_resolver_construction_is_thread_safe(tmp_path: Path, stub_client):
    """Two concurrent verify_finding calls for the same eval don't race the resolver init."""
    import threading

    _make_project(tmp_path)

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="api/app.py", line=6, category="flexibility/adaptability",
            severity="major", description="hardcoded provider dependency",
        )

    canned = {
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4")},
        "confidence": 0.5,
        "evidence_summary": "x",
    }

    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=stub_client(canned, canned, canned, canned),
        model="gemma:4",
    )

    results: list = []
    errors: list = []

    def worker():
        try:
            r = service.verify_finding("eval-1", "flexibility", "f1")
            results.append(r)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Expected no errors; got {errors}"
    assert len(results) == 4
    # All four runs should have used the same cached resolver (only one was built)
    assert len(service._resolvers) == 1
