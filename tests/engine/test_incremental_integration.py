"""End-to-end integration test for incremental analysis."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quodeq.analysis.fingerprint import build_fingerprint, save_fingerprint, load_fingerprint
from quodeq.analysis.incremental import classify_files, carry_forward_findings


class TestIncrementalEndToEnd:
    def test_full_cycle_fingerprint_classify_carry_forward(self, tmp_path):
        """Simulate: first run creates fingerprint, second run detects changes."""
        # === First run: create files and fingerprint ===
        (tmp_path / "auth.py").write_text("def login(): pass")
        (tmp_path / "utils.py").write_text("def helper(): pass")
        (tmp_path / "routes.py").write_text("from auth import login")

        files = ["auth.py", "utils.py", "routes.py"]
        fp1 = build_fingerprint(tmp_path, files, "security", standards_dir=None)
        evidence_dir_1 = tmp_path / "run1"
        evidence_dir_1.mkdir()
        save_fingerprint(fp1, evidence_dir_1)

        # Simulate first run produced findings
        prev_jsonl = evidence_dir_1 / "security_evidence.jsonl"
        prev_jsonl.write_text(
            json.dumps({"p": "Conf", "d": "security", "t": "violation", "file": "auth.py", "line": 1, "w": "issue"}) + "\n"
            + json.dumps({"p": "Conf", "d": "security", "t": "compliance", "file": "utils.py", "line": 1, "w": "ok"}) + "\n"
            + json.dumps({"p": "Conf", "d": "security", "t": "violation", "file": "routes.py", "line": 5, "w": "route issue"}) + "\n"
        )

        # === Second run: change auth.py only ===
        (tmp_path / "auth.py").write_text("def login(): secure_pass()")

        classification = classify_files(
            src=tmp_path, files=files,
            prev_fingerprint=fp1, standards_dir=None,
            dimension="security", language="python",
        )

        # auth.py changed, routes.py depends on auth.py (imports it)
        assert "auth.py" in classification.to_analyze
        assert "routes.py" in classification.to_analyze
        assert "utils.py" in classification.unchanged

        # Carry forward utils.py findings only
        output_jsonl = tmp_path / "run2" / "security_evidence.jsonl"
        output_jsonl.parent.mkdir()
        carried = carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)
        assert carried == 1  # only the utils.py compliance finding

        # Verify carried-forward content
        lines = [json.loads(l) for l in output_jsonl.read_text().strip().split("\n")]
        assert len(lines) == 1
        assert lines[0]["file"] == "utils.py"
        assert lines[0]["t"] == "compliance"

    def test_no_changes_carries_everything(self, tmp_path):
        """When nothing changed, all findings are carried forward."""
        (tmp_path / "a.py").write_text("same")
        (tmp_path / "b.py").write_text("also_same")

        files = ["a.py", "b.py"]
        fp = build_fingerprint(tmp_path, files, "reliability", standards_dir=None)

        prev_jsonl = tmp_path / "prev.jsonl"
        prev_jsonl.write_text(
            json.dumps({"p": "FT", "d": "reliability", "t": "violation", "file": "a.py", "line": 1, "w": "issue"}) + "\n"
            + json.dumps({"p": "FT", "d": "reliability", "t": "compliance", "file": "b.py", "line": 1, "w": "ok"}) + "\n"
        )

        classification = classify_files(
            src=tmp_path, files=files,
            prev_fingerprint=fp, standards_dir=None,
            dimension="reliability", language="python",
        )

        assert len(classification.to_analyze) == 0
        assert classification.unchanged == {"a.py", "b.py"}

        output_jsonl = tmp_path / "output.jsonl"
        carried = carry_forward_findings(prev_jsonl, output_jsonl, classification.unchanged)
        assert carried == 2

    def test_fingerprint_round_trip(self, tmp_path):
        """Fingerprint saved and loaded correctly."""
        (tmp_path / "file.py").write_text("content")
        fp = build_fingerprint(tmp_path, ["file.py"], "security", standards_dir=None)

        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        save_fingerprint(fp, evidence_dir)

        loaded = load_fingerprint(evidence_dir, "security")
        assert loaded is not None
        assert loaded["dimension"] == "security"
        assert loaded["file_hashes"]["file.py"] == fp["file_hashes"]["file.py"]

    def test_new_dimension_gets_full_analysis(self, tmp_path):
        """A dimension never evaluated before should trigger full analysis."""
        (tmp_path / "a.py").write_text("content")

        # No previous fingerprint for "performance"
        classification = classify_files(
            src=tmp_path, files=["a.py"],
            prev_fingerprint=None, standards_dir=None,
            dimension="performance", language="python",
        )
        assert classification.full_reanalysis is True
        assert set(classification.to_analyze) == {"a.py"}
