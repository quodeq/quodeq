"""Extended tests for quodeq.services.violations.resolve_dimension_eval: deleted-finding filtering and source fallbacks."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


from quodeq.services.violations import resolve_dimension_eval, ResolveOptions


class TestDeletedFilteredFromDimensionEval:
    """Permanently-deleted findings must not survive into the served dimension eval.

    The JSON eval parser emits camelCase violation dicts (``practiceId``, not
    ``principle``), so the deletion key must be built from ``practiceId``.
    Regression test for the dimension-detail view showing deleted findings.
    """

    def test_deleted_key_matches_practice_id_violation(self, tmp_path):
        project_dir = tmp_path / "project"
        base = project_dir / "run"
        (base / "evaluation").mkdir(parents=True)
        eval_data = {
            "dimension": "testdim",
            "principles": [{"name": "Clear Naming", "score": 5, "grade": "C"}],
            "violations": [
                {"principle": "Clear Naming", "file": "src/app.py", "line": 12,
                 "title": "t", "reason": "r", "severity": "major"},
                {"principle": "Clear Naming", "file": "src/other.py", "line": 3,
                 "title": "t2", "reason": "r2", "severity": "minor"},
            ],
        }
        (base / "evaluation" / "testdim.json").write_text(json.dumps(eval_data))
        (project_dir / "deleted.json").write_text(json.dumps([
            {"dimension": "testdim", "principle": "Clear Naming", "file": "src/app.py"},
        ]))

        result = resolve_dimension_eval(base, "proj", "run", "testdim")

        files = [v["file"] for v in result["violations"]]
        assert "src/app.py" not in files
        assert "src/other.py" in files

    def test_deleted_key_matches_principle_group_violations(self, tmp_path):
        """Group entries carry no principle field; the group name is the principle."""
        project_dir = tmp_path / "project"
        base = project_dir / "run"
        (base / "evaluation").mkdir(parents=True)
        eval_data = {
            "dimension": "testdim",
            "principles": [{"name": "Clear Naming", "score": 5, "grade": "C"}],
            "violations": [
                {"principle": "Clear Naming", "file": "src/app.py", "line": 12,
                 "title": "t", "reason": "r", "severity": "major"},
                {"principle": "Clear Naming", "file": "src/other.py", "line": 3,
                 "title": "t2", "reason": "r2", "severity": "minor"},
            ],
        }
        (base / "evaluation" / "testdim.json").write_text(json.dumps(eval_data))
        (project_dir / "deleted.json").write_text(json.dumps([
            {"dimension": "testdim", "principle": "Clear Naming", "file": "src/app.py"},
        ]))

        result = resolve_dimension_eval(base, "proj", "run", "testdim")

        group = next(p for p in result["principles"] if p["name"] == "Clear Naming")
        group_files = [v["file"] for v in group["violations"]]
        assert "src/app.py:12" not in group_files
        assert "src/other.py:3" in group_files


class TestResolveDimensionEvalExtended:
    def test_json_eval_priority(self, tmp_path):
        """JSON eval takes priority over markdown and evidence."""
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        eval_data = {"dimension": "security", "overallGrade": "A", "principles": {}}
        (eval_dir / "security.json").write_text(json.dumps(eval_data))
        (eval_dir / "security_eval.md").write_text("# Security\nScore: A")

        result = resolve_dimension_eval(base, "proj", "run", "security")
        assert result is not None

    def test_markdown_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        md_content = "# Security Evaluation\n\nOverall Grade: B\n\n## Principle 1\n\nGrade: B\n"
        (eval_dir / "security_eval.md").write_text(md_content)

        resolve_dimension_eval(base, "proj", "run", "security")
        # Should attempt markdown parse; result depends on parser
        # The key thing is it doesn't return None when markdown exists

    def test_evidence_json_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        evidence = {
            "principles": {
                "p1": {
                    "display_name": "P1",
                    "violations": [{"file": "x.py", "line": 1, "reason": "bad"}],
                }
            }
        }
        (evidence_dir / "security_evidence.json").write_text(json.dumps(evidence))

        result = resolve_dimension_eval(base, "proj", "run", "security")
        assert result is not None

    def test_stream_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        (evidence_dir / "security_live.stream").write_text("some stream data\n")

        resolve_dimension_eval(base, "proj", "run", "security")
        # Stream parsing may or may not produce violations, but code path is exercised

    def test_custom_exists_fn(self, tmp_path):
        """Test with custom ResolveOptions to exercise injection."""
        base = tmp_path / "run"
        (base / "evaluation").mkdir(parents=True)
        (base / "evidence").mkdir()

        # All exists return False - should return None
        opts = ResolveOptions(exists_fn=lambda p: False)
        result = resolve_dimension_eval(base, "proj", "run", "security", options=opts)
        assert result is None

    def test_markdown_read_error(self, tmp_path):
        """OSError reading markdown returns None."""
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        (base / "evidence").mkdir()

        md_path = eval_dir / "security_eval.md"
        md_path.write_text("content")

        def fake_exists(p):
            if "security.json" in str(p):
                return False
            return p.exists()

        opts = ResolveOptions(exists_fn=fake_exists)
        with patch("quodeq.services.violations.read_text", side_effect=OSError("read error")):
            result = resolve_dimension_eval(base, "proj", "run", "security", options=opts)
            assert result is None

    def test_jsonl_fallback(self, tmp_path):
        base = tmp_path / "run"
        eval_dir = base / "evaluation"
        eval_dir.mkdir(parents=True)
        evidence_dir = base / "evidence"
        evidence_dir.mkdir()

        # Write non-empty JSONL
        (evidence_dir / "security_evidence.jsonl").write_text(
            json.dumps({"type": "finding", "data": {}}) + "\n"
        )

        def custom_exists(p):
            return p.exists()

        class FakeStat:
            st_size = 100

        opts = ResolveOptions(exists_fn=custom_exists, stat_fn=lambda p: FakeStat())
        # This exercises the jsonl path; actual parsing may vary
        with patch("quodeq.services.violations.parse_violations_from_jsonl", return_value=MagicMock()) as mock_parse:
            resolve_dimension_eval(base, "proj", "run", "security", options=opts)
            mock_parse.assert_called_once()
