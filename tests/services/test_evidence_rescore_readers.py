import json
from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.evidence_rescore import EvidenceScoreRequest, score_dimension_from_evidence


def test_injected_readers_are_used(tmp_path: Path):
    ev = tmp_path / "evidence"
    ev.mkdir()
    (ev / "clean-architecture_evidence.jsonl").write_text(json.dumps({
        "schema_version": 1, "req": "CLEA-DEP-01", "t": "violation", "file": "a.py",
        "line": 1, "severity": "minor", "w": "t", "reason": "r", "vt": "x",
        "p": "Dependency Rule", "d": "clean-architecture", "snippet": "s",
    }) + "\n")
    calls = []

    def req_map_reader(*args, **kwargs):
        calls.append("req_map")
        return {}

    def refs_reader(*args, **kwargs):
        calls.append("refs")
        return {}

    request = EvidenceScoreRequest(
        dismissed=set(), deleted=set(), source_file_count=10, files_read=10,
        params=DEFAULT_PARAMS, standard_dirs_fn=lambda: (tmp_path, tmp_path),
        req_map_reader=req_map_reader, refs_reader=refs_reader,
    )
    score_dimension_from_evidence(tmp_path, "clean-architecture", request)
    assert {"req_map", "refs"} <= set(calls), (
        "req_map_reader groups the violation; refs_reader enriches the "
        "judgment because compiled_dir, req, and dimension are all set"
    )
