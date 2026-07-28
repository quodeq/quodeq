"""Cache replays must be distinguishable from this scan's own findings.

The live evaluation feed filters on carried_forward. It is stamped here,
at the only place that knows a finding came from the cache rather than
from the running scan.
"""
import json
from pathlib import Path

from quodeq.analysis.cache.dimension_runner import _write_findings


def _finding(title: str) -> dict:
    return {
        "file": "a.py", "line": 1, "t": "violation", "w": title,
        "p": "P1", "d": "security", "req": "X-1", "severity": "minor",
        "snippet": "x", "reason": "r",
    }


def test_write_findings_stamps_carried_forward(tmp_path: Path):
    jsonl = tmp_path / "security_evidence.jsonl"
    _write_findings(jsonl, [_finding("carry-a")], append=False, emit_events=False)
    written = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert written[0]["carried_forward"] is True


def test_write_findings_does_not_mutate_the_source_dicts(tmp_path: Path):
    """The dicts belong to the cache entry. Stamping in place risks the
    persist watcher writing the flag back into the cache, which would make
    a later fresh scan of the same file look carried."""
    jsonl = tmp_path / "security_evidence.jsonl"
    source = [_finding("carry-a")]
    _write_findings(jsonl, source, append=False, emit_events=False)
    assert "carried_forward" not in source[0]


from unittest.mock import patch

from quodeq.analysis.cache.entry import CacheEntry
from tests.analysis.cache.test_dimension_runner import (
    _make_callbacks, _make_ctx, _make_dummy_evidence, _setup, cache,
)


def test_only_cache_replays_are_flagged(tmp_path: Path, cache):
    """a.py is a cache hit, b.py is dispatched. Exactly one is flagged."""
    from quodeq.analysis.cache.dimension_helpers import build_cache_key_for_file
    from quodeq.analysis.cache.dimension_runner import process_dimension_with_cache

    config, _src = _setup(tmp_path, {"a.py": "x", "b.py": "y"})

    key = build_cache_key_for_file(config, "a.py", "security")
    cache.put(key, CacheEntry(
        key=key, schema_version=1,
        findings=[dict(_finding("carry-a"), file="a.py")],
        files_read=1, file_path="a.py", dimension="security",
        model_id="test-model",
    ))

    def fake_dispatch(cfg, dim_id, idx, ctx, callbacks):
        jsonl = (cfg.work_dir or cfg.src) / f"{dim_id}_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with jsonl.open("a") as out:
            out.write(json.dumps(dict(_finding("fresh-b"), file="b.py", p="P2")) + "\n")
            out.write(json.dumps({"_marker": "file_done", "file": "b.py", "status": "ok"}) + "\n")
        return _make_dummy_evidence(files_read=1)

    with patch(
        "quodeq.analysis.cache.dimension_runner.process_dimension_with_subagents",
        new=fake_dispatch,
    ):
        process_dimension_with_cache(
            config, "security", 1, _make_ctx(), _make_callbacks(), cache=cache,
        )

    jsonl_path = (config.work_dir or config.src) / "security_evidence.jsonl"
    lines = [json.loads(ln) for ln in jsonl_path.read_text().splitlines() if ln.strip()]
    by_title = {ln["w"]: ln for ln in lines if "_marker" not in ln}
    assert by_title["carry-a"].get("carried_forward") is True
    assert by_title["fresh-b"].get("carried_forward", False) is False
