"""Tests for quodeq.config.standards_fetcher — ASVS fetch with mocked HTTP."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.config.standards_fetcher import fetch_asvs_l1


def _asvs_payload() -> dict:
    """Minimal ASVS-shaped JSON for testing."""
    return {
        "Requirements": [
            {
                "ShortName": "Authentication",
                "Items": [
                    {
                        "Items": [
                            {
                                "Shortcode": "V2.1.1",
                                "Description": "Verify passwords are at least 12 characters.",
                                "L1": {"Required": True},
                                "CWE": [521],
                            },
                            {
                                "Shortcode": "V2.1.2",
                                "Description": "Not required at L1.",
                                "L1": {"Required": False},
                                "CWE": [],
                            },
                        ]
                    }
                ],
            }
        ],
    }


@pytest.fixture()
def _mock_urlopen(monkeypatch):
    """Patch urlopen to return _asvs_payload as bytes."""
    content = json.dumps(_asvs_payload()).encode()
    response = MagicMock()
    response.read.return_value = content
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)
    with patch("quodeq.config.standards_fetcher.urllib.request.urlopen", return_value=response) as mock:
        yield mock, content


class TestFetchAsvsL1:
    def test_writes_l1_requirements(self, tmp_path: Path, _mock_urlopen) -> None:
        count = fetch_asvs_l1(tmp_path, skip_integrity=True)
        assert count == 1
        out = json.loads((tmp_path / "asvs" / "level1.json").read_text())
        assert out["level"] == 1
        assert len(out["requirements"]) == 1
        assert out["requirements"][0]["id"] == "V2.1.1"

    def test_dry_run_does_not_write(self, tmp_path: Path, _mock_urlopen) -> None:
        fetch_asvs_l1(tmp_path, dry_run=True, skip_integrity=True)
        assert not (tmp_path / "asvs" / "level1.json").exists()

    def test_hash_mismatch_raises(self, tmp_path: Path, _mock_urlopen, monkeypatch) -> None:
        monkeypatch.setenv("QUODEQ_ASVS_SHA256", "badhash")
        with pytest.raises(ValueError, match="integrity check failed"):
            fetch_asvs_l1(tmp_path)

    def test_urlopen_called_with_timeout(self, tmp_path: Path, _mock_urlopen) -> None:
        mock_urlopen, _ = _mock_urlopen
        fetch_asvs_l1(tmp_path, skip_integrity=True)
        from quodeq.config.standards_fetcher import _DEFAULT_FETCH_TIMEOUT_S
        assert mock_urlopen.call_args.kwargs.get("timeout") == _DEFAULT_FETCH_TIMEOUT_S

    def test_first_download_rejected_without_hash(self, tmp_path: Path, monkeypatch) -> None:
        """Without QUODEQ_ASVS_SHA256, first download is rejected (CWE-353)."""
        monkeypatch.delenv("QUODEQ_ASVS_SKIP_INTEGRITY", raising=False)
        monkeypatch.delenv("QUODEQ_ASVS_SHA256", raising=False)
        content = json.dumps(_asvs_payload()).encode()
        response = MagicMock()
        response.read.return_value = content
        response.__enter__ = lambda self: self
        response.__exit__ = MagicMock(return_value=False)
        with patch("quodeq.config.standards_fetcher.urllib.request.urlopen", return_value=response):
            with pytest.raises(ValueError, match="No ASVS hash configured"):
                fetch_asvs_l1(tmp_path)

    def test_first_download_accepted_with_skip_integrity(self, tmp_path: Path, monkeypatch) -> None:
        """With skip_integrity=True, download proceeds without hash."""
        monkeypatch.delenv("QUODEQ_ASVS_SKIP_INTEGRITY", raising=False)
        monkeypatch.delenv("QUODEQ_ASVS_SHA256", raising=False)
        content = json.dumps(_asvs_payload()).encode()
        response = MagicMock()
        response.read.return_value = content
        response.__enter__ = lambda self: self
        response.__exit__ = MagicMock(return_value=False)
        with patch("quodeq.config.standards_fetcher.urllib.request.urlopen", return_value=response):
            fetch_asvs_l1(tmp_path, skip_integrity=True)  # should not raise
