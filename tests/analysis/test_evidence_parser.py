"""parse_evidence_file's options seam: injecting fake readers/sinks."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.evidence_parser import parse_evidence_file
from quodeq.analysis.run_types import AnalysisContext, RunConfig
from quodeq.core.evidence.parser import EvidenceParseOptions


def _config(tmp_path: Path) -> RunConfig:
    return RunConfig(src=tmp_path, language="python")


def _ctx() -> AnalysisContext:
    return AnalysisContext(
        dimensions_data={}, date_str="2026-09-25", template="", subagent_template="", total=1,
    )


def test_uses_injected_options_instead_of_the_production_defaults(tmp_path):
    """options is a call-time seam: when set, parse_evidence_file must parse
    with it instead of calling the concrete evidence_parse_options."""
    jsonl = tmp_path / "security_evidence.jsonl"
    jsonl.write_text(
        '{"file":"a.py","line":1,"t":"violation","p":"P1","d":"security",'
        '"req":"S-1","severity":"minor","snippet":"x","reason":"r"}\n',
        encoding="utf-8",
    )

    calls: list = []

    def _fake_req_map_reader(*args, **kwargs):
        calls.append((args, kwargs))
        return {}

    # compiled_dir must be set: the reader is only called when a directory
    # is present to hand it (see req_mapping._resolve_req_to_principle_map).
    options = EvidenceParseOptions(compiled_dir=tmp_path, req_map_reader=_fake_req_map_reader)

    evidence = parse_evidence_file(_config(tmp_path), _ctx(), jsonl, files_read=1, options=options)

    assert calls, "the injected options' req_map_reader must have been used"
    assert evidence.language == "python"
