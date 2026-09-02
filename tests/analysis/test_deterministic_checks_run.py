"""Wiring deterministic checkers into a run — applying checks to a run.

Split from test_deterministic_checks.py: findings reach the per-dim
evidence and JSONL and events.jsonl; RunConfig wiring through
apply_checks_for_run and the DimensionRunner call site. Shared fixtures
live in tests/analysis/_deterministic_checks_fixtures.py.
"""
from __future__ import annotations

import json

from quodeq.core.evidence.model import Evidence
from tests.analysis._deterministic_checks_fixtures import (  # noqa: F401 -- project/compiled are pytest fixtures
    SOURCES,
    STANDARD,
    compiled,
    project,
)


class TestApplyToARun:
    def _evidence(self):
        return Evidence(repository="r", language="python", date="2026-08-02",
                        source_file_count=3, files_read=3, coverage_pct=100.0)

    def _apply(self, project, compiled_dir, tmp_path):
        from quodeq.analysis.checks.runner import apply_deterministic_checks

        jsonl = tmp_path / "run" / "evidence" / "clean-architecture_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        jsonl.touch()
        evidence = self._evidence()
        added = apply_deterministic_checks(
            evidence, root=project, source_files=SOURCES,
            dimension="clean-architecture", compiled_dir=compiled_dir, jsonl_path=jsonl,
        )
        return added, evidence, jsonl

    def test_findings_land_in_the_evidence_under_their_principle(
        self, project, compiled, tmp_path,
    ):
        added, evidence, _ = self._apply(project, compiled(STANDARD), tmp_path)

        assert added == 2
        assert sorted(evidence.principles) == [
            "Dependency Rule", "Independence from Frameworks",
        ]
        violated = evidence.principles["Dependency Rule"]
        assert [v["file"] for v in violated.violations] == ["app/domain/order.py"]
        assert violated.metrics["violating"] == 1, "metrics must be recomputed"

        clean = evidence.principles["Independence from Frameworks"]
        assert len(clean.compliance) == 1
        assert clean.violations == [], "a clean check must not score as a defect"

    def test_findings_merge_into_an_existing_principle(self, project, compiled, tmp_path):
        from quodeq.analysis.checks.runner import apply_deterministic_checks
        from quodeq.core.evidence.model import PrincipleEvidence

        jsonl = tmp_path / "run" / "evidence" / "d.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        evidence = self._evidence()
        evidence.principles["Dependency Rule"] = PrincipleEvidence(
            practice_id="Dependency Rule", display_name="Dependency Rule",
            dimension="clean-architecture", severity="major",
            violations=[{"file": "other.py", "line": 1}],
        )

        apply_deterministic_checks(
            evidence, root=project, source_files=SOURCES,
            dimension="clean-architecture", compiled_dir=compiled(STANDARD),
            jsonl_path=jsonl,
        )

        assert len(evidence.principles["Dependency Rule"].violations) == 2

    def test_findings_reach_the_jsonl_and_the_event_log(self, project, compiled, tmp_path):
        _added, _evidence, jsonl = self._apply(project, compiled(STANDARD), tmp_path)

        wire = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines()]
        assert [(w["p"], w["t"]) for w in wire] == [
            ("CLEA-DEP-06", "violation"), ("CLEA-FRM-01", "compliance"),
        ]
        assert wire[0]["file"] == "app/domain/order.py"

        events = jsonl.parent.parent / "events.jsonl"
        assert events.is_file(), "the SQL projection reads events.jsonl, not the dim JSONL"
        payloads = [json.loads(line)["payload"]
                    for line in events.read_text(encoding="utf-8").splitlines()]
        assert [p["practice_id"] for p in payloads] == ["CLEA-DEP-06", "CLEA-FRM-01"]

    def test_the_wire_rows_round_trip_back_to_judgments(self, project, compiled, tmp_path):
        """Whatever we write must parse the way an LLM finding would."""
        from quodeq.core.evidence._jsonl import parse_jsonl_line

        _added, _evidence, jsonl = self._apply(project, compiled(STANDARD), tmp_path)

        parsed = parse_jsonl_line(jsonl.read_text(encoding="utf-8").splitlines()[0])
        assert parsed is not None
        judgment, _refs = parsed
        assert judgment.practice_id == "CLEA-DEP-06"
        assert judgment.severity == "major"
        assert judgment.file == "app/domain/order.py"

    def test_nothing_found_writes_nothing(self, project, compiled, tmp_path):
        clean = {"principles": [{"name": "Dependency Rule", "requirements": [
            {"id": "CLEA-DEP-06", "text": "x"}]}]}

        added, evidence, jsonl = self._apply(project, compiled(clean), tmp_path)

        assert added == 0
        assert evidence.principles == {}
        assert jsonl.read_text(encoding="utf-8") == ""
        assert not (jsonl.parent.parent / "events.jsonl").exists()

    def test_an_unwritable_jsonl_still_updates_the_evidence(
        self, project, compiled, tmp_path,
    ):
        """A persistence failure must not cost the in-memory findings."""
        from quodeq.analysis.checks.runner import apply_deterministic_checks

        evidence = self._evidence()

        added = apply_deterministic_checks(
            evidence, root=project, source_files=SOURCES,
            dimension="clean-architecture", compiled_dir=compiled(STANDARD),
            jsonl_path=tmp_path / "nonexistent" / "deep" / "x.jsonl",
        )

        assert added == 2
        assert "Dependency Rule" in evidence.principles


class TestRunWiring:
    """Adapting a RunConfig into checker inputs, and the call site itself."""

    def _config(self, project, compiled_dir, tmp_path, *, manifest=True):
        from types import SimpleNamespace

        from quodeq.analysis._types import RunConfig

        work_dir = tmp_path / "run" / "evidence"
        work_dir.mkdir(parents=True, exist_ok=True)
        return RunConfig(
            src=project, language="python",
            standards_dir=compiled_dir.parent,
            work_dir=work_dir,
            manifest=SimpleNamespace(source_files=list(SOURCES)) if manifest else None,
        )

    def test_findings_land_using_the_projects_full_source_list(
        self, project, compiled, tmp_path,
    ):
        """The graph needs outer modules too, so it uses the project-wide list
        rather than whatever this dimension happened to dispatch."""
        from quodeq.analysis.checks.runner import apply_checks_for_run

        config = self._config(project, compiled(STANDARD), tmp_path)
        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=3, files_read=3, coverage_pct=100.0)

        added = apply_checks_for_run(config, "clean-architecture", evidence)

        assert added == 2
        assert "Dependency Rule" in evidence.principles
        assert (tmp_path / "run" / "evidence"
                / "clean-architecture_evidence.jsonl").is_file()

    def test_a_run_with_no_manifest_adds_nothing(self, project, compiled, tmp_path):
        from quodeq.analysis.checks.runner import apply_checks_for_run

        config = self._config(project, compiled(STANDARD), tmp_path, manifest=False)
        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=0, files_read=0, coverage_pct=0.0)

        assert apply_checks_for_run(config, "clean-architecture", evidence) == 0

    def test_a_broken_config_never_raises(self, tmp_path):
        """The call site is inside a dimension run; it must not be able to fail it."""
        from unittest.mock import MagicMock

        from quodeq.analysis.checks.runner import apply_checks_for_run

        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=0, files_read=0, coverage_pct=0.0)

        assert apply_checks_for_run(MagicMock(), "clean-architecture", evidence) == 0

    def test_the_dimension_runner_calls_it_with_the_parsed_evidence(self):
        from unittest.mock import MagicMock, patch

        from quodeq.analysis.dimension_runner import DimensionRunner

        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=1, files_read=1, coverage_pct=100.0)
        ctx = MagicMock()
        ctx.total = 1

        with patch("quodeq.analysis.dimension_runner.process_dimension_with_cache",
                   return_value=evidence), \
             patch("quodeq.analysis.dimension_runner.apply_checks_for_run",
                   return_value=0) as applied:
            result = DimensionRunner().run(MagicMock(), "clean-architecture", 1, ctx)

        assert result is evidence
        assert applied.call_args.args[1:] == ("clean-architecture", evidence)

    def test_a_failed_dimension_runs_no_checks(self):
        """No evidence means the dimension did not run; nothing to add to."""
        from unittest.mock import MagicMock, patch

        from quodeq.analysis.dimension_runner import DimensionRunner

        with patch("quodeq.analysis.dimension_runner.process_dimension_with_cache",
                   return_value=None), \
             patch("quodeq.analysis.dimension_runner.apply_checks_for_run") as applied:
            DimensionRunner().run(MagicMock(), "clean-architecture", 1, MagicMock())

        applied.assert_not_called()
