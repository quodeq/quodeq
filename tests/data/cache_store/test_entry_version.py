"""quodeq_version() stays "" when the package has no version, with no swallowed import."""
from __future__ import annotations

import quodeq
from quodeq.data.cache_store.entry import quodeq_version


def test_version_is_empty_string_when_package_version_is_none(monkeypatch) -> None:
    monkeypatch.setattr(quodeq, "__version__", None)
    assert quodeq_version() == ""
