"""FilesystemActionProvider.delete_evaluation drops the projects-list cache."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from quodeq.services.filesystem import FilesystemActionProvider


def _provider() -> FilesystemActionProvider:
    provider = FilesystemActionProvider()
    provider._projects = MagicMock()
    return provider


def test_invalidates_projects_cache_after_a_delete() -> None:
    provider = _provider()
    with patch.object(provider._evaluations, "delete", return_value=True):
        assert provider.delete_evaluation("ext-run-1") is True
    provider._projects.invalidate.assert_called_once_with()


def test_does_not_invalidate_when_the_delete_was_refused() -> None:
    provider = _provider()
    with patch.object(provider._evaluations, "delete", return_value=False):
        assert provider.delete_evaluation("ext-run-1") is False
    provider._projects.invalidate.assert_not_called()
