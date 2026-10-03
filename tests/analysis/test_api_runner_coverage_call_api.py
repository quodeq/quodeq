"""Extended tests for _api_runner.py: call_api parsing, lossy flags and response_format."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

import httpx

from quodeq.analysis._api_runner import ApiRunnerConfig, call_api


# ---------------------------------------------------------------------------
# call_api
# ---------------------------------------------------------------------------

def _mock_response(content: str) -> MagicMock:
    msg = MagicMock(content=content)
    choice = MagicMock(message=msg)
    return MagicMock(choices=[choice])


def _local_config() -> ApiRunnerConfig:
    return ApiRunnerConfig(model="test-model", api_base="http://localhost:11434/v1", api_key="ollama")


def _cloud_config() -> ApiRunnerConfig:
    return ApiRunnerConfig(model="gpt-x", api_base="https://api.openai.com/v1", api_key="sk-x")


_GOOD = (
    '{"req":"A-1","t":"violation","file":"a.py","line":1,'
    '"severity":"minor","w":"one","snippet":"x = 1","reason":"r"}'
)
_GOOD2 = (
    '{"req":"B-2","t":"compliance","file":"b.py","line":2,'
    '"severity":"minor","w":"two","snippet":"y = 2","reason":"r"}'
)
_BAD_MISSING_REASON = (
    '{"req":"C-3","t":"violation","file":"c.py","line":3,'
    '"severity":"minor","w":"bad","snippet":"z"}'
)


class TestCallApi:
    def _run(self, content=None, side_effect=None, config=None):
        with patch("openai.OpenAI") as mock_oa:
            client = MagicMock()
            if side_effect is not None:
                client.chat.completions.create.side_effect = side_effect
            else:
                client.chat.completions.create.return_value = _mock_response(content)
            mock_oa.return_value.__enter__.return_value = client
            findings, lossy = call_api("prompt", config or _local_config())
            return findings, lossy, mock_oa, client

    def test_clean_wrapped_array(self):
        findings, lossy, *_ = self._run(f'{{"findings":[{_GOOD},{_GOOD2}]}}')
        assert len(findings) == 2
        assert lossy is False

    def test_one_bad_finding_drops_only_itself(self):
        findings, lossy, *_ = self._run(f'{{"findings":[{_GOOD},{_BAD_MISSING_REASON}]}}')
        assert len(findings) == 1
        assert findings[0]["req"] == "A-1"
        assert lossy is False

    def test_bare_concatenated_findings(self):
        findings, lossy, *_ = self._run(f'{_GOOD}\n{_GOOD2}')
        assert {f["req"] for f in findings} == {"A-1", "B-2"}
        assert lossy is False

    def test_garbled_response_not_lossy(self):
        findings, lossy, *_ = self._run("I cannot evaluate this code.")
        assert findings == []
        assert lossy is False

    def test_network_error_is_lossy(self):
        findings, lossy, *_ = self._run(side_effect=httpx.ReadTimeout("upstream"))
        assert findings == []
        assert lossy is True

    def test_cloud_sets_json_object_response_format(self):
        _, _, _, client = self._run(f'{{"findings":[{_GOOD}]}}', config=_cloud_config())
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["response_format"] == {"type": "json_object"}

    def test_local_omits_json_object_response_format(self):
        _, _, _, client = self._run(f'{{"findings":[{_GOOD}]}}', config=_local_config())
        kwargs = client.chat.completions.create.call_args.kwargs
        assert "response_format" not in kwargs

    def test_dropped_findings_logged_with_count(self, caplog):
        # The quodeq logger has propagate=False, so caplog (which adds a handler
        # to the root logger) won't see its records. Re-enable propagation
        # temporarily so pytest's caplog handler receives the messages.
        quodeq_logger = logging.getLogger("quodeq")
        orig_propagate = quodeq_logger.propagate
        quodeq_logger.propagate = True
        try:
            with caplog.at_level(logging.WARNING, logger="quodeq.analysis._api_runner"):
                findings, lossy, *_ = self._run(
                    f'{{"findings":[{_GOOD},{_BAD_MISSING_REASON},{_BAD_MISSING_REASON}]}}'
                )
        finally:
            quodeq_logger.propagate = orig_propagate
        assert len(findings) == 1
        assert lossy is False
        assert any("dropped 2" in r.message for r in caplog.records)

    def test_connection_error_is_lossy_with_generic_message(self, caplog):
        import openai as _openai
        exc = _openai.APIConnectionError(request=httpx.Request("POST", "http://localhost:11434/v1"))
        with caplog.at_level(logging.WARNING, logger="quodeq.analysis._api_runner"):
            # quodeq logger has propagate=False; flip it so caplog sees the record.
            qlog = logging.getLogger("quodeq")
            orig = qlog.propagate
            qlog.propagate = True
            try:
                findings, lossy, *_ = self._run(side_effect=exc)
            finally:
                qlog.propagate = orig
        assert findings == []
        assert lossy is True
        msgs = " ".join(r.message for r in caplog.records)
        assert "timed out" not in msgs
        assert "call failed" in msgs

    def test_drop_counter_field_wins_over_run_configs_counter(self, tmp_path):
        """I1: the single-agent fallback and consolidated builders carry the
        run's drop counter directly on the config (no run_config, so the
        API cache writer stays off for those paths). That field must be
        checked before run_config's counter."""
        from quodeq.analysis.run_types import RunConfig

        direct_counter = RunConfig(src=tmp_path, language="python").drop_counter
        run_config = RunConfig(src=tmp_path, language="python")
        config = ApiRunnerConfig(
            model="test-model", api_base="http://localhost:11434/v1", api_key="ollama",
            drop_counter=direct_counter, run_config=run_config,
        )

        findings, lossy, *_ = self._run(
            f'{{"findings":[{_GOOD},{_BAD_MISSING_REASON}]}}', config=config,
        )

        assert len(findings) == 1
        stats = direct_counter.consume()
        assert stats.dropped == 1
        assert stats.kept == 1
        # run_config's own (distinct) counter never saw the drop.
        assert run_config.drop_counter.consume().parsed == 0
