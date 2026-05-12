from datetime import datetime, timezone
from pathlib import Path

import pytest

from quodeq.resolver.models import FindingInput
from quodeq.verifier.models import Verdict
from quodeq.verifier.service import (
    VerifierService,
    LocatedFinding,
    FindingNotFound,
    _is_substitutability_finding,
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
            "Q5": {"answer": "yes", "cite": "MANIFEST"},
        },
        "findings": {
            "default_implementation": {"value": "FilesystemActionProvider", "cite": None},
            "override_mechanism": {"value": "provider param", "cite": None},
            "abstraction_in_use": {"value": "ActionProvider", "cite": "MANIFEST"},
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
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4", "Q5")},
        "findings": {
            "default_implementation": {"value": "X", "cite": None},
            "override_mechanism": {"value": "Y", "cite": None},
            "abstraction_in_use": {"value": "Z", "cite": "MANIFEST"},
        },
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


def test_classifier_accepts_substitutability_findings():
    cases = [
        ("Platform-specific filesystem dependency", "flexibility/adaptability"),
        ("Hardcoded class FilesystemProvider", "flexibility/adaptability"),
        ("Hardcoded implementation of Provider", "flexibility/adaptability"),
        ("Concrete coupling to FilesystemActionProvider", "flexibility/adaptability"),
        ("Tight coupling to concrete class", "flexibility/adaptability"),
        ("Missing abstraction for storage backend", "flexibility/adaptability"),
        ("Violates DIP by depending on FileSystem", "flexibility/adaptability"),
    ]
    for title, category in cases:
        assert _is_substitutability_finding(title, category), (
            f"expected applicable: title={title!r} category={category!r}"
        )


def test_classifier_uses_reason_text_when_title_is_uninformative():
    """Real evaluations often have a terse title; the substitutability
    language lives in the reason body. The classifier must look there."""
    # The exact finding the user flagged: title says 'Hardcoded output
    # filename' but reason talks about coupling and switching.
    title = "Hardcoded output filename"
    category = "flexibility/adaptability"
    reason = (
        "The default provider is hardcoded to use FilesystemActionProvider, "
        "which couples the application logic directly to the local filesystem "
        "and prevents easy switching to cloud storage without code modification."
    )
    assert _is_substitutability_finding(title, category, reason)


def test_classifier_catches_platform_specific_in_reason():
    title = "Platform-specific logic not abstracted"
    category = "flexibility/adaptability"
    reason = (
        "The function directly calls read_run_data which relies on the local "
        "file system (Path objects), making the logic dependent on a specific "
        "storage implementation rather than an abstraction layer."
    )
    assert _is_substitutability_finding(title, category, reason)


def test_classifier_rejects_out_of_scope_findings():
    cases = [
        ("Hardcoded output filename", "flexibility/adaptability"),
        ("Hardcoded path /tmp/foo", "flexibility/adaptability"),
        ("Magic number 42", "maintainability/readability"),
        ("Duplicate code block", "maintainability/readability"),
        ("Long function exceeds 100 lines", "maintainability/readability"),
        ("Variable name is unclear", "maintainability/readability"),
    ]
    for title, category in cases:
        assert not _is_substitutability_finding(title, category), (
            f"expected NOT applicable: title={title!r} category={category!r}"
        )


def test_service_short_circuits_out_of_scope_finding(tmp_path: Path, stub_client):
    """A finding the classifier rejects skips the LLM and returns NOT_APPLICABLE."""
    _make_project(tmp_path)

    def locate(eval_id, dim, fid):
        return LocatedFinding(
            file="api/app.py",
            line=6,
            category="flexibility/adaptability",
            severity="minor",
            description="Hardcoded output filename",
        )

    # Empty script: any call to the stub client would raise (script exhausted).
    client = stub_client()  # no canned response — proves we never call Ollama

    service = VerifierService(
        evaluations_root=tmp_path / "evals",
        project_root=tmp_path,
        finding_locator=locate,
        client=client,
        model="gemma:4",
    )
    result = service.verify_finding(
        evaluation_id="eval-1",
        dimension="flexibility",
        finding_id="f1",
    )
    assert result.verdict == Verdict.NOT_APPLICABLE
    assert client.calls == [], "no Ollama call should have happened"
    # Still recorded in the per-evaluation store and audit log
    assert (tmp_path / "evals" / "eval-1" / "verifications.db").exists()
    log_dir = tmp_path / "evals" / "eval-1" / "verifier" / result.verification_id
    assert (log_dir / "manifest.json").exists()


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
        "checklist": {q: {"answer": "yes", "cite": "MANIFEST"} for q in ("Q1", "Q2", "Q3", "Q4", "Q5")},
        "findings": {
            "default_implementation": {"value": "X", "cite": None},
            "override_mechanism": {"value": "Y", "cite": None},
            "abstraction_in_use": {"value": "Z", "cite": "MANIFEST"},
        },
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
