"""Stream-event parsing is shared wire-format logic, not analysis logic.

services/_violations_stream and services/_violations_jsonl imported these
helpers from analysis/ (three grandfathered baseline entries). The pure
parsers move inward to core/stream/events.py and the file-reading counters
to data/fs/stream_files.py, so both layers reach them without a
services -> analysis arrow.
"""
from __future__ import annotations

import json


class TestPureParsers:
    def test_parse_stream_event_handles_blank_and_invalid(self):
        from quodeq.core.stream.events import parse_stream_event

        assert parse_stream_event("") is None
        assert parse_stream_event("   ") is None
        assert parse_stream_event("not json") is None
        assert parse_stream_event('{"type": "assistant"}') == {"type": "assistant"}

    def test_extract_files_from_assistant_event(self):
        from quodeq.core.stream.events import extract_files_from_event

        event = {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}},
                {"type": "tool_use", "name": "Grep", "input": {"path": "b.py"}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": "skip.py"}},
            ]},
        }
        assert extract_files_from_event(event) == {"a.py", "b.py"}

    def test_extract_files_from_non_dict_is_empty(self):
        from quodeq.core.stream.events import extract_files_from_event

        assert extract_files_from_event(["nope"]) == set()

    def test_text_extractors_cover_the_event_types(self):
        from quodeq.core.stream.events import TEXT_EXTRACTORS

        assert set(TEXT_EXTRACTORS) == {"assistant", "result", "item.completed"}
        assert TEXT_EXTRACTORS["result"]({"result": "done"}) == ["done"]


class TestStreamFileCounters:
    def test_count_files_in_stream(self, tmp_path):
        from quodeq.data.fs.stream_files import count_files_in_stream

        stream = tmp_path / "s.stream"
        stream.write_text("\n".join([
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "x.py"}},
            ]}}),
            "",
            "garbage",
        ]), encoding="utf-8")

        assert count_files_in_stream(stream) == {"x.py"}

    def test_count_files_missing_stream_is_empty(self, tmp_path):
        from quodeq.data.fs.stream_files import count_files_in_stream

        assert count_files_in_stream(tmp_path / "nope.stream") == set()

    def test_count_jsonl_lines_skips_blanks(self, tmp_path):
        from quodeq.data.fs.stream_files import count_jsonl_lines

        f = tmp_path / "e.jsonl"
        f.write_text('{"a":1}\n\n{"b":2}\n', encoding="utf-8")
        assert count_jsonl_lines(f) == 2

    def test_count_jsonl_lines_missing_is_zero(self, tmp_path):
        from quodeq.data.fs.stream_files import count_jsonl_lines

        assert count_jsonl_lines(tmp_path / "nope.jsonl") == 0


def test_analysis_shims_keep_their_public_names():
    """Existing analysis callers and tests import these from analysis/stream;
    the modules stay as re-export shims so nothing downstream moves."""
    from quodeq.analysis.stream.counters import (
        count_files_in_stream, extract_files_from_event, parse_stream_event,
    )
    from quodeq.analysis.stream.event_text import TEXT_EXTRACTORS
    from quodeq.core.stream import events as core_events
    from quodeq.data.fs import stream_files

    assert extract_files_from_event is core_events.extract_files_from_event
    assert parse_stream_event is core_events.parse_stream_event
    assert TEXT_EXTRACTORS is core_events.TEXT_EXTRACTORS
    assert count_files_in_stream is stream_files.count_files_in_stream


def test_violation_services_no_longer_import_analysis():
    import quodeq.services._violations_jsonl as vj
    import quodeq.services._violations_stream as vs

    for mod in (vs, vj):
        src = open(mod.__file__).read()
        assert "quodeq.analysis" not in src, mod.__name__
