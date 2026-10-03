"""API runner parsing: drop accounting, the vt taxonomy field, drop stats and config defaults."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis import _drop_stats
from quodeq.analysis._api_runner import ApiRunnerConfig, call_api
from quodeq.analysis._api_schema import _Finding, parse_findings

from ._api_runner_helpers import _mock_raw_client


class TestParserDropAccounting:
    """Every finding-shaped object the model emits but we can't keep must be
    counted, so a systemic loss is visible in the logs instead of silent."""

    def test_counts_finding_missing_req_as_dropped(self):
        # A finding-shaped object missing the required `req`. Today it is
        # silently recursed away and NOT counted; it must count as dropped.
        raw = json.dumps({"findings": [
            {"t": "violation", "file": "a.py", "line": 5, "w": "x",
             "snippet": "code", "reason": "bad"},  # no req
        ]})
        findings, dropped = parse_findings(raw)
        assert findings == []
        assert dropped == 1

    def test_does_not_count_non_finding_noise(self):
        # A stray container/noise object that does not look like a finding
        # must NOT inflate the dropped count.
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        raw = '{"note": "analysis complete"}' + json.dumps({"findings": [valid]})
        findings, dropped = parse_findings(raw)
        assert len(findings) == 1
        assert dropped == 0

    def test_recovers_real_findings_nested_in_finding_shaped_wrapper(self):
        # A wrapper that happens to share >=2 finding field names (severity,
        # reason) but NESTS a real finding must not have that finding swallowed.
        # Counting the wrapper as a drop AND stopping recursion would lose it.
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        raw = json.dumps({"severity": "major", "reason": "run summary", "items": [valid]})
        findings, dropped = parse_findings(raw)
        assert len(findings) == 1
        assert findings[0]["req"] == "R1"
        assert dropped == 0


class TestFindingVtTaxonomy:
    """The optional 'vt' taxonomy code must survive _Finding validation, or
    every fresh API run scores with taxonomy_used=False (free-text reason
    grouping counts near-duplicates as distinct types and depresses scores)."""

    _BASE = {
        "req": "S-CON-3", "t": "violation", "file": "src/a.py", "line": 3,
        "severity": "critical", "w": "eval usage",
        "snippet": "eval(x)", "reason": "Direct code injection via eval.",
    }

    def test_vt_survives_validate_and_dump(self):
        dumped = _Finding.model_validate({**self._BASE, "vt": "code-injection"}).model_dump()
        assert dumped["vt"] == "code-injection"

    def test_vt_defaults_to_none_when_absent(self):
        dumped = _Finding.model_validate(self._BASE).model_dump()
        assert dumped["vt"] is None


class TestDropStatsRecording:
    """call_api feeds the per-run drop-ratio accumulator (issue #606).

    The per-call WARNING already counts dropped findings; recording the same
    (dropped, kept) pair into ``_drop_stats`` lets the run loop surface ONE
    aggregate signal instead of N scattered lines.
    """

    @pytest.fixture(autouse=True)
    def _isolated_counter(self, monkeypatch):
        # call_api records through the module-default counter; swap in a
        # fresh instance so nothing leaks in from (or out to) other tests.
        monkeypatch.setattr(
            _drop_stats, "_default_counter", _drop_stats.DropStatsCounter())

    def test_call_with_malformed_finding_records_drop_and_kept(self, api_config):
        valid = {"req": "R1", "t": "violation", "file": "a.py", "line": 5,
                 "severity": "minor", "w": "x", "snippet": "code", "reason": "bad"}
        malformed = {"t": "violation", "file": "b.py", "line": 1, "w": "y",
                     "snippet": "code", "reason": "bad"}  # no req -> dropped
        content = json.dumps({"findings": [valid, malformed]})
        client = _mock_raw_client(content)
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            call_api("prompt", api_config)
        stats = _drop_stats.consume()
        assert stats.dropped == 1
        assert stats.kept == 1

    def test_failed_call_records_nothing(self, api_config):
        client = MagicMock()
        client.chat.completions.create.side_effect = httpx.ReadTimeout("timeout")
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            call_api("prompt", api_config)
        assert _drop_stats.consume().parsed == 0

    def test_call_with_run_config_records_on_the_run_scoped_counter(self, api_config, tmp_path):
        """A config carrying a RunConfig (the pool/CLI path) records onto
        its ``drop_counter`` -- shared by every pool worker thread of that
        run -- instead of the process-wide default."""
        from dataclasses import replace

        from quodeq.analysis.run_types import RunConfig

        run_config = RunConfig(src=tmp_path, language="python")
        scoped_config = replace(api_config, run_config=run_config)
        malformed = {"t": "violation", "file": "b.py", "line": 1, "w": "y",
                     "snippet": "code", "reason": "bad"}  # no req -> dropped
        content = json.dumps({"findings": [malformed]})
        client = _mock_raw_client(content)
        with patch("openai.OpenAI") as mock_oa:
            mock_oa.return_value.__enter__.return_value = client
            call_api("prompt", scoped_config)

        stats = run_config.drop_counter.consume()
        assert stats.dropped == 1
        # The process-wide default counter must stay untouched.
        assert _drop_stats.consume().parsed == 0


class TestApiRunnerConfig:
    """ApiRunnerConfig dataclass."""

    def test_defaults(self):
        cfg = ApiRunnerConfig(model="test", api_base="http://localhost/v1")
        assert cfg.api_key == ""
        assert cfg.temperature == 0.1
        assert cfg.max_tokens is None

    def test_custom_values(self):
        cfg = ApiRunnerConfig(
            model="gpt-4o",
            api_base="https://api.openai.com/v1",
            api_key="sk-...",
            temperature=0.0,
            max_tokens=4096,
        )
        assert cfg.temperature == 0.0
        assert cfg.max_tokens == 4096
