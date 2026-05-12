"""End-to-end verifier integration tests (with stub Ollama client)."""

from pathlib import Path

from quodeq.resolver import Resolver
from quodeq.resolver.models import FindingInput
from quodeq.verifier import Verifier
from quodeq.verifier.models import Verdict
from tests.verifier.fixtures.gemma_responses import (
    CONFIRMED_HARDCODED,
    DI_WITH_DEFAULT_FALSE_POSITIVE,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_fixture(root: Path) -> None:
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


def test_verifier_returns_false_positive_for_di_with_default(tmp_path: Path, stub_client):
    _make_fixture(tmp_path)
    resolver = Resolver(project_root=tmp_path)
    resolver.build_index()
    finding = FindingInput(
        file="api/app.py",
        line=6,
        category="flexibility/adaptability",
        severity="major",
    )
    manifest = resolver.build_manifest(finding)
    # The canned response cites paths that aren't in this fixture's evidence,
    # so the citation validator will downgrade some answers to unknown. The
    # integration test verifies the orchestration only — that we get a
    # reasonable verdict given a clean response and a valid manifest.
    client = stub_client(DI_WITH_DEFAULT_FALSE_POSITIVE)
    verifier = Verifier(project_root=tmp_path, client=client, model="gemma:4")

    result = verifier.verify(manifest, finding)
    # The canned response's checklist answers are all "yes" — even after
    # citation downgrade, Q3 cites "MANIFEST" (always valid). Q4 may be
    # downgraded to "unknown" depending on what's in the rendered evidence.
    # Either result.verdict is false_positive (all yes survive) or
    # inconclusive (some yes downgraded to unknown). It must NOT be confirmed.
    assert result.verdict in (Verdict.FALSE_POSITIVE, Verdict.INCONCLUSIVE)
    assert result.model == "gemma:4"


def test_verifier_returns_confirmed_for_hardcoded(tmp_path: Path, stub_client):
    _make_fixture(tmp_path)
    resolver = Resolver(project_root=tmp_path)
    resolver.build_index()
    finding = FindingInput(
        file="api/app.py",
        line=6,
        category="flexibility/adaptability",
        severity="major",
    )
    manifest = resolver.build_manifest(finding)
    client = stub_client(CONFIRMED_HARDCODED)
    verifier = Verifier(project_root=tmp_path, client=client, model="gemma:4")

    result = verifier.verify(manifest, finding)
    # Q3 == "no" in the canned response. The v8 rule requires Q3=yes for
    # confirmed (Q1=yes AND Q2=no AND Q3=yes). With Q3=no, verdict is inconclusive.
    assert result.verdict == Verdict.INCONCLUSIVE
