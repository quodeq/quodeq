from pathlib import Path

from quodeq.resolver.cache import IndexCache
from quodeq.resolver.indexer import build_index
from quodeq.resolver.queries import (
    callers_of,
    param_type_users,
    subclasses_of,
    where_defined,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build(tmp_path: Path) -> IndexCache:
    _write(
        tmp_path / "services" / "base.py",
        """\
from typing import Protocol

class ActionProvider(Protocol):
    ...
""",
    )
    _write(
        tmp_path / "services" / "filesystem.py",
        """\
from .base import ActionProvider

class FilesystemActionProvider(ActionProvider):
    pass
""",
    )
    _write(
        tmp_path / "api" / "app.py",
        """\
from services.base import ActionProvider


def _default_provider() -> ActionProvider:
    from services.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()


def create_app(provider: ActionProvider | None = None):
    provider = provider or _default_provider()
    return provider
""",
    )
    cache = IndexCache(tmp_path / "symbols.db")
    build_index(cache, tmp_path)
    return cache


def test_where_defined_finds_class(tmp_path: Path):
    cache = _build(tmp_path)
    loc = where_defined(cache, "ActionProvider", kind="class")
    assert loc is not None
    assert loc.file.endswith("services/base.py")
    assert loc.line == 3
    cache.close()


def test_subclasses_of_returns_known_implementer(tmp_path: Path):
    cache = _build(tmp_path)
    subs = subclasses_of(cache, "ActionProvider")
    names = sorted(s.file for s in subs)
    assert any(n.endswith("services/filesystem.py") for n in names)
    cache.close()


def test_param_type_users_finds_create_app(tmp_path: Path):
    cache = _build(tmp_path)
    hits = param_type_users(cache, "ActionProvider")
    assert any(h.file.endswith("api/app.py") for h in hits)
    cache.close()


def test_callers_of_finds_default_provider_call(tmp_path: Path):
    cache = _build(tmp_path)
    hits = callers_of(cache, "_default_provider")
    assert any(h.file.endswith("api/app.py") for h in hits)
    cache.close()
