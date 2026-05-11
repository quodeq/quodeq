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
                description="hardcoded provider",
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
