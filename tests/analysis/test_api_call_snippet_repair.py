"""The snippet repair re-ask (issue #1222).

qwen3.8:27b-mlx emits findings without the required verbatim ``snippet`` at
scale: on a full run, 2556 of 2582 parsed findings dropped, every one for
``snippet:missing``, while the run still looked healthy. The requirement
itself is deliberate (a finding must quote the code it accuses), so the fix
is not to relax it but to give the model one chance to complete its own
snippetless findings: a single follow-up call replaying them alongside the
source it was already given. No recursion; still-snippetless findings drop
for good.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("openai", reason="requires the openai SDK")

from quodeq.analysis import _drop_stats
from quodeq.analysis._api_call import ApiRunnerConfig, _call_api
from quodeq.analysis._api_response import (
    _MAX_REPAIR_FINDINGS,
    _REPAIR_PROMPT,
    _finish_call,
    _merge_repaired,
    _snippetless,
)
from quodeq.analysis._api_schema import _parse_findings
from quodeq.config.analysis_env import finding_repair_disabled

_GOOD = {
    "req": "A-1", "t": "violation", "file": "a.py", "line": 1,
    "w": "one", "snippet": "x = 1", "reason": "r",
}
_SNIPPETLESS = {
    "req": "B-2", "t": "violation", "file": "b.py", "line": 2,
    "w": "two", "reason": "r",
}
_REPAIRED = {**_SNIPPETLESS, "snippet": "y = 2"}
# Dropped WITH a snippet present: the failure is elsewhere, so a repair
# re-ask cannot help and must not fire.
_SNIPPET_PRESENT = {
    "req": "C-3", "t": "violation", "file": "c.py", "line": 3,
    "w": "bad", "snippet": "z",
}


def _payload(*findings: dict) -> str:
    return json.dumps({"findings": list(findings)})


def _config() -> ApiRunnerConfig:
    return ApiRunnerConfig(
        model="test-model", api_base="http://localhost:11434/v1", api_key="ollama",
    )


@pytest.fixture(autouse=True)
def _isolated_drop_stats():
    """_finish_call records on the run-wide counter; keep tests independent."""
    _drop_stats.consume()
    yield
    _drop_stats.consume()


class TestDroppedSink:
    def test_sink_receives_the_rejected_dicts(self):
        sink: list[dict] = []
        findings, dropped = _parse_findings(
            _payload(_GOOD, _SNIPPETLESS), dropped_sink=sink,
        )
        assert len(findings) == 1
        assert dropped == 1
        assert sink == [_SNIPPETLESS]

    def test_no_sink_still_counts(self):
        findings, dropped = _parse_findings(_payload(_GOOD, _SNIPPETLESS))
        assert (len(findings), dropped) == (1, 1)


class TestSnippetless:
    def test_missing_snippet_with_identity_qualifies(self):
        assert _snippetless([_SNIPPETLESS]) == [_SNIPPETLESS]

    def test_empty_string_snippet_qualifies(self):
        node = {**_SNIPPETLESS, "snippet": ""}
        assert _snippetless([node]) == [node]

    def test_snippet_present_means_some_other_failure(self):
        # e.g. dropped for a missing reason: re-asking about the snippet
        # cannot help, so it must not trigger (or ride along on) a repair.
        assert _snippetless([_SNIPPET_PRESENT]) == []

    def test_node_without_identity_fields_is_unrepairable(self):
        assert _snippetless([{"t": "violation", "line": 1, "w": "x"}]) == []


class TestMergeRepaired:
    def test_accepts_only_findings_answering_the_asked_nodes(self):
        kept: list[dict] = []
        invented = {**_REPAIRED, "req": "Z-9", "file": "z.py"}
        added = _merge_repaired(kept, [_REPAIRED, invented], [_SNIPPETLESS])
        assert added == 1
        assert kept == [_REPAIRED]

    def test_line_may_shift_to_the_quoted_span(self):
        kept: list[dict] = []
        moved = {**_REPAIRED, "line": 7}
        assert _merge_repaired(kept, [moved], [_SNIPPETLESS]) == 1

    def test_duplicate_of_a_kept_finding_does_not_double(self):
        kept = [dict(_REPAIRED)]
        assert _merge_repaired(kept, [dict(_REPAIRED)], [_SNIPPETLESS]) == 0
        assert len(kept) == 1


class TestFinishCallRepair:
    def test_recovered_findings_rejoin_the_kept_list(self):
        reask = MagicMock(return_value=[dict(_REPAIRED)])
        findings, lossy = _finish_call(
            "test-model", "stop", _payload(_GOOD, _SNIPPETLESS), 0.0, reask=reask,
        )
        assert lossy is False
        assert {f["req"] for f in findings} == {"A-1", "B-2"}
        (asked,) = reask.call_args.args
        assert asked == [_SNIPPETLESS]

    def test_drop_stats_describe_the_final_outcome(self):
        reask = MagicMock(return_value=[dict(_REPAIRED)])
        _finish_call(
            "test-model", "stop", _payload(_GOOD, _SNIPPETLESS), 0.0, reask=reask,
        )
        stats = _drop_stats.consume()
        assert stats.dropped == 0
        assert stats.kept == 2
        assert "snippet:missing" not in stats.reasons

    def test_failed_repair_keeps_first_pass_findings_and_counts(self):
        reask = MagicMock(return_value=[])
        findings, _ = _finish_call(
            "test-model", "stop", _payload(_GOOD, _SNIPPETLESS), 0.0, reask=reask,
        )
        assert [f["req"] for f in findings] == ["A-1"]
        stats = _drop_stats.consume()
        assert stats.dropped == 1
        assert stats.reasons.get("snippet:missing") == 1

    def test_no_drops_means_no_reask(self):
        reask = MagicMock()
        _finish_call("test-model", "stop", _payload(_GOOD), 0.0, reask=reask)
        reask.assert_not_called()

    def test_unrepairable_drops_do_not_reask(self):
        # Dropped WITH a snippet present: the failure is elsewhere, and a
        # repair call would burn a model round-trip for nothing.
        reask = MagicMock()
        _finish_call("test-model", "stop", _payload(_GOOD, _SNIPPET_PRESENT), 0.0, reask=reask)
        reask.assert_not_called()

    def test_kill_switch_disables_the_reask(self, monkeypatch):
        monkeypatch.setenv("QUODEQ_DISABLE_FINDING_REPAIR", "1")
        reask = MagicMock()
        findings, _ = _finish_call(
            "test-model", "stop", _payload(_GOOD, _SNIPPETLESS), 0.0, reask=reask,
        )
        reask.assert_not_called()
        assert [f["req"] for f in findings] == ["A-1"]


class TestCallApiRepairRoundTrip:
    def _client(self, responses: list):
        client = MagicMock()
        client.chat.completions.create.side_effect = responses
        return client

    @staticmethod
    def _response(content: str) -> MagicMock:
        msg = MagicMock(content=content)
        choice = MagicMock(message=msg, finish_reason="stop")
        return MagicMock(choices=[choice])

    def _run(self, responses: list):
        with patch("openai.OpenAI") as mock_oa:
            client = self._client(responses)
            mock_oa.return_value.__enter__.return_value = client
            findings, lossy = _call_api("the source", _config())
        return findings, lossy, client

    def test_second_call_replays_findings_and_source(self):
        findings, lossy, client = self._run([
            self._response(_payload(_GOOD, _SNIPPETLESS)),
            self._response(_payload(_REPAIRED)),
        ])
        assert lossy is False
        assert {f["req"] for f in findings} == {"A-1", "B-2"}
        assert client.chat.completions.create.call_count == 2
        repair_kwargs = client.chat.completions.create.call_args_list[1].kwargs
        messages = repair_kwargs["messages"]
        # system + original user + assistant replay + repair instruction
        assert [m["role"] for m in messages] == [
            "system", "user", "assistant", "user",
        ]
        assert messages[1]["content"] == "the source"
        assert "B-2" in messages[2]["content"]
        assert messages[3]["content"] == _REPAIR_PROMPT

    def test_repair_call_failure_is_not_lossy(self):
        import httpx

        findings, lossy, client = self._run([
            self._response(_payload(_GOOD, _SNIPPETLESS)),
            httpx.ReadTimeout("boom"),
        ])
        assert lossy is False
        assert [f["req"] for f in findings] == ["A-1"]

    def test_clean_response_makes_one_call(self):
        _, _, client = self._run([self._response(_payload(_GOOD))])
        assert client.chat.completions.create.call_count == 1

    def test_repair_batch_is_capped(self):
        many = [
            {**_SNIPPETLESS, "req": f"B-{i}", "line": i + 1}
            for i in range(_MAX_REPAIR_FINDINGS + 5)
        ]
        _, _, client = self._run([
            self._response(_payload(_GOOD, *many)),
            self._response(_payload()),
        ])
        repair_kwargs = client.chat.completions.create.call_args_list[1].kwargs
        replayed = json.loads(repair_kwargs["messages"][2]["content"])["findings"]
        assert len(replayed) == _MAX_REPAIR_FINDINGS


class TestKillSwitchParsing:
    @pytest.mark.parametrize("raw", ["1", "true", " TRUE ", "yes", "on"])
    def test_truthy_values_disable(self, raw):
        assert finding_repair_disabled({"QUODEQ_DISABLE_FINDING_REPAIR": raw})

    @pytest.mark.parametrize("raw", ["", "0", "false", "off"])
    def test_other_values_keep_it_on(self, raw):
        assert not finding_repair_disabled({"QUODEQ_DISABLE_FINDING_REPAIR": raw})

    def test_unset_keeps_it_on(self):
        assert not finding_repair_disabled({})
