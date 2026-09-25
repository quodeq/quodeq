"""Tests for quodeq.services._violations_stream — stream event parsing."""
from __future__ import annotations

import json


class TestTryParseTextLine:
    def test_non_json_line(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        result = _try_parse_text_line("not a json", "sec", set())
        assert result is None

    def test_invalid_json(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        result = _try_parse_text_line("{bad json", "sec", set())
        assert result is None

    def test_missing_principle(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        result = _try_parse_text_line(json.dumps({"t": "violation"}), "sec", set())
        assert result is None

    def test_invalid_type(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        result = _try_parse_text_line(json.dumps({"p": "P1", "t": "unknown"}), "sec", set())
        assert result is None

    def test_valid_violation(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        line = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1})
        result = _try_parse_text_line(line, "sec", set())
        assert result is not None
        assert result[0] == "violation"

    def test_valid_compliance(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        line = json.dumps({"p": "P2", "t": "compliance", "file": "b.py"})
        result = _try_parse_text_line(line, "sec", set())
        assert result is not None
        assert result[0] == "compliance"

    def test_dedup_by_seen_key(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        seen = set()
        line = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1})
        result1 = _try_parse_text_line(line, "sec", seen)
        assert result1 is not None
        result2 = _try_parse_text_line(line, "sec", seen)
        assert result2 is None

    def test_snippet_stripping(self):
        from quodeq.services._violations_stream import _try_parse_text_line
        line = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "snippet": "  code  "})
        result = _try_parse_text_line(line, "sec", set())
        assert result is not None
        _, entry = result
        if entry.snippet:
            assert entry.snippet == entry.snippet.strip()


class TestParseEntriesFromTexts:
    def test_empty_texts(self):
        from quodeq.services._violations_stream import _parse_entries_from_texts
        v, c = _parse_entries_from_texts([], "sec", set())
        assert v == []
        assert c == []

    def test_mixed_findings(self):
        from quodeq.services._violations_stream import _parse_entries_from_texts
        texts = [
            json.dumps({"p": "P1", "t": "violation", "file": "a.py"}) + "\n"
            + json.dumps({"p": "P2", "t": "compliance", "file": "b.py"}),
        ]
        v, c = _parse_entries_from_texts(texts, "sec", set())
        assert len(v) == 1
        assert len(c) == 1


class TestStreamAccumulator:
    def test_creation(self):
        from quodeq.services._violations_stream import _StreamAccumulator
        acc = _StreamAccumulator(dimension="sec")
        assert acc.dimension == "sec"
        assert acc.violations == []
        assert acc.compliance == []
        assert acc.seen == set()
        assert acc.files_read == set()


class TestParseStreamLine:
    def test_invalid_json(self):
        from quodeq.services._violations_stream import _parse_stream_line, _StreamAccumulator
        acc = _StreamAccumulator(dimension="sec")
        _parse_stream_line("not json", acc)
        assert acc.violations == []

    def test_unknown_event_type(self):
        from quodeq.services._violations_stream import _parse_stream_line, _StreamAccumulator
        acc = _StreamAccumulator(dimension="sec")
        _parse_stream_line(json.dumps({"type": "unknown_event"}), acc)
        assert acc.violations == []
        # A list-shaped line and a dict with a non-string `type` must be
        # skipped the same way, without raising and without blocking a
        # later, well-formed line on the same accumulator.
        _parse_stream_line(json.dumps([1]), acc)
        _parse_stream_line(json.dumps({"type": []}), acc)
        valid_text = json.dumps({"p": "P1", "t": "violation", "file": "a.py", "line": 1})
        valid_event = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": valid_text},
        ]}})
        _parse_stream_line(valid_event, acc)
        assert len(acc.violations) == 1
        assert acc.violations[0].practice_id == "P1"


class TestParseViolationsFromStream:
    def test_missing_file(self, tmp_path):
        from quodeq.services._violations_stream import parse_violations_from_stream
        from quodeq.services.violation_context import ViolationContext
        ctx = ViolationContext(dimension="sec", run_id="r1", project="p1")
        result = parse_violations_from_stream(tmp_path / "missing.stream", ctx)
        assert result is None

    def test_missing_file_logs_a_warning(self, tmp_path, caplog):
        """A missing stream file must still log the read-failure warning,
        exactly as it did before ``iter_stream_lines`` existed -- a plain
        early return (with no log call) would silently drop this signal."""
        import logging
        from quodeq.services._violations_stream import parse_violations_from_stream
        from quodeq.services.violation_context import ViolationContext
        ctx = ViolationContext(dimension="sec", run_id="r1", project="p1")
        missing = tmp_path / "missing.stream"
        with caplog.at_level(logging.WARNING, logger="quodeq.services._violations_stream"):
            result = parse_violations_from_stream(missing, ctx)
        assert result is None
        assert "Failed to read stream file" in caplog.text
        assert str(missing) in caplog.text

    def test_valid_stream_file(self, tmp_path):
        from quodeq.services._violations_stream import parse_violations_from_stream
        from quodeq.services.violation_context import ViolationContext
        stream = tmp_path / "stream.jsonl"
        # Write a minimal stream event (no findings in it)
        stream.write_text(json.dumps({"type": "message_start"}) + "\n")
        ctx = ViolationContext(dimension="sec", run_id="r1", project="p1")
        result = parse_violations_from_stream(stream, ctx)
        assert result is not None
        assert result.dimension == "sec"
        assert result.partial is True
