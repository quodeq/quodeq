"""Extended tests for standards_fetcher — version resolution and URL host validation."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quodeq.config.standards_fetcher import (
    _ASVS_ALLOWED_HOSTS,
    _DEFAULT_ASVS_VERSION,
    _asvs_version,
    fetch_asvs_l1,
)


class TestAsvsVersion:
    def test_default_version(self):
        assert _asvs_version() == _DEFAULT_ASVS_VERSION

    def test_override_takes_priority(self):
        assert _asvs_version(override="5.0.0") == "5.0.0"

    def test_env_override(self):
        assert _asvs_version(env={"QUODEQ_ASVS_VERSION": "4.1.0"}) == "4.1.0"

    def test_env_missing_uses_default(self):
        assert _asvs_version(env={}) == _DEFAULT_ASVS_VERSION


class TestFetchAsvsL1HostValidation:
    def test_blocked_host_raises(self, tmp_path):
        with patch("quodeq.config.standards_fetcher.get_asvs_url", return_value="https://evil.com/asvs.json"):
            with pytest.raises(ValueError, match="not in the allowlist"):
                fetch_asvs_l1(tmp_path)

    def test_allowed_hosts_includes_github(self):
        assert "raw.githubusercontent.com" in _ASVS_ALLOWED_HOSTS
        assert "github.com" in _ASVS_ALLOWED_HOSTS
        assert "owasp.org" in _ASVS_ALLOWED_HOSTS
