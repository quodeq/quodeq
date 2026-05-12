"""Opt-in real-Ollama integration test.

Skipped by default. Enable with `QUODEQ_VERIFIER_LIVE=1`.

This test runs the full pipeline against a real local Gemma instance. It is
intentionally NOT in CI — Ollama isn't installed in CI, model weights are
large, and the test is a smoke test to confirm the v7.2 prompt still
produces a clean structured response on the current Gemma build.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from quodeq.resolver import Resolver
from quodeq.resolver.models import FindingInput
from quodeq.verifier import Verifier
from quodeq.verifier.models import Verdict


pytestmark = pytest.mark.skipif(
    os.environ.get("QUODEQ_VERIFIER_LIVE") != "1",
    reason="Live Ollama test gated by QUODEQ_VERIFIER_LIVE=1",
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


def test_di_with_default_yields_false_positive_on_live_gemma(tmp_path: Path):
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

    model = os.environ.get("QUODEQ_VERIFIER_MODEL", "gemma:4")
    verifier = Verifier(project_root=tmp_path, model=model)
    result = verifier.verify(manifest, finding)

    assert result.verdict == Verdict.FALSE_POSITIVE, (
        f"Expected false_positive on the DI-with-default fixture; got "
        f"{result.verdict}.\nResponse: {result.response}"
    )
    assert result.response.findings.default_implementation.value == "FilesystemActionProvider"
    assert result.response.findings.abstraction_in_use.value == "ActionProvider"
