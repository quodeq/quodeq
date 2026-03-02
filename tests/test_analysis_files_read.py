import json
import tempfile
from pathlib import Path

from codecompass.evaluate.lib.analysis import extract_jsonl_evidence


def _write_stream(path: Path, events: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_extract_jsonl_evidence_returns_files_read():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/a.py"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/b.py"}},
                    {"type": "tool_use", "name": "Grep", "input": {"pattern": "foo"}},
                    {"type": "text", "text": '{"p":"key","t":"violation","file":"a.py","severity":"minor","reason":"r"}'},
                ]
            },
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stream = Path(tmp) / "stream.json"
        jsonl = Path(tmp) / "out.jsonl"
        _write_stream(stream, events)
        files_read = extract_jsonl_evidence(str(stream), str(jsonl), "dim")
        assert files_read == 2   # only Read tool calls, Grep excluded


def test_extract_jsonl_evidence_deduplicates_paths():
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/a.py"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/a.py"}},  # duplicate
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/b.py"}},
                ]
            },
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stream = Path(tmp) / "stream.json"
        jsonl = Path(tmp) / "out.jsonl"
        _write_stream(stream, events)
        files_read = extract_jsonl_evidence(str(stream), str(jsonl), "dim")
        assert files_read == 2   # /repo/a.py deduplicated


def test_extract_jsonl_evidence_returns_zero_on_empty():
    with tempfile.TemporaryDirectory() as tmp:
        stream = Path(tmp) / "stream.json"
        jsonl = Path(tmp) / "out.jsonl"
        stream.write_text("")
        files_read = extract_jsonl_evidence(str(stream), str(jsonl), "dim")
        assert files_read == 0


def test_extract_jsonl_evidence_item_completed_reads():
    events = [
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/c.py"}},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/repo/d.py"}},
                ],
            },
        }
    ]
    with tempfile.TemporaryDirectory() as tmp:
        stream = Path(tmp) / "stream.json"
        jsonl = Path(tmp) / "out.jsonl"
        _write_stream(stream, events)
        files_read = extract_jsonl_evidence(str(stream), str(jsonl), "dim")
        assert files_read == 2
