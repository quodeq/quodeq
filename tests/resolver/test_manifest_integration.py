from pathlib import Path

from quodeq.resolver import Resolver
from quodeq.resolver.models import FindingInput


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_fixture(root: Path) -> None:
    """Reproduce the FilesystemActionProvider DI-with-default fixture."""
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


def test_manifest_for_di_with_default_fixture(tmp_path: Path):
    _make_fixture(tmp_path)
    resolver = Resolver(project_root=tmp_path)
    resolver.build_index()

    finding = FindingInput(
        file="api/app.py",
        line=6,                # the `from services.filesystem import …` line
        category="flexibility/adaptability",
        severity="major",
    )
    manifest = resolver.build_manifest(finding)

    assert manifest.target_file_role == "composition_root"
    assert manifest.referenced_symbol == "FilesystemActionProvider"
    assert manifest.referenced_symbol_defined_at is not None
    assert manifest.referenced_symbol_defined_at.file.endswith("services/filesystem.py")
    assert "ActionProvider" in manifest.referenced_symbol_bases

    assert manifest.abstraction == "ActionProvider"
    assert manifest.abstraction_defined_at is not None
    assert manifest.abstraction_defined_at.file.endswith("services/base.py")
    assert manifest.abstraction_kind == "Protocol"
    assert manifest.abstraction_implementations_prod >= 1

    assert manifest.target_enclosing_function is not None
    assert manifest.target_enclosing_function.name == "_default_provider"
    assert manifest.target_enclosing_function.lazy_imports_inside_body is True

    assert manifest.target_parent_function is not None
    assert manifest.target_parent_function.name == "create_app"
    assert manifest.target_parent_seam_at is not None
    assert manifest.target_parent_seam_at.file.endswith("api/app.py")
    assert "or _default_provider()" in (manifest.target_parent_seam_pattern or "")
