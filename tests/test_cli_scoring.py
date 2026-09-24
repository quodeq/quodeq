"""_cli_scoring._read_report / dim_evidence_counts: report-file reads.

_read_report used to json.loads the dimension report file inline; it now
reads through data.fs.report_parser.finding_details.read_eval_report (which
returns None for a missing file, raises on malformed JSON). The try/except
around the call must keep the old "missing or unparseable -> {}" contract.

_read_report itself is private with no public re-export, so it's exercised
here through dim_evidence_counts -- its only public-reachable caller,
re-exported from quodeq.cli_evaluation (see that module's compat imports).
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.cli_evaluation import dim_evidence_counts


class TestDimEvidenceCounts:
    def test_missing_report_falls_back_to_zeros(self, tmp_path: Path) -> None:
        assert dim_evidence_counts(tmp_path, "security") == (0, 0)

    def test_malformed_json_falls_back_to_zeros(self, tmp_path: Path) -> None:
        (tmp_path / "security.json").write_text("{not json", encoding="utf-8")
        assert dim_evidence_counts(tmp_path, "security") == (0, 0)

    def test_non_dict_json_falls_back_to_zeros(self, tmp_path: Path) -> None:
        (tmp_path / "security.json").write_text("[1, 2, 3]", encoding="utf-8")
        assert dim_evidence_counts(tmp_path, "security") == (0, 0)

    def test_reads_counts_from_report(self, tmp_path: Path) -> None:
        payload = {"sourceFileCount": 10, "filesRead": 8}
        (tmp_path / "security.json").write_text(json.dumps(payload), encoding="utf-8")
        assert dim_evidence_counts(tmp_path, "security") == (10, 8)
