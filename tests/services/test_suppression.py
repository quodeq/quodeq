"""The single seam that decides whether an evidence row is suppressed.

Dismiss/delete identity keys have diverged from their consumers more than
once (dismiss matching (req, file, line) vs the dashboard's practiceId
delete key). These tests pin the key shapes and, crucially, pin that the
live-progress tally and the dashboard's parse path agree on them.
"""
import json

import pytest

from quodeq.services.suppression import SuppressionMatcher, build_matcher, load_req_to_principle, matcher_for
from quodeq.services.suppression_keys import SuppressionKeys


def _evidence(**over):
    row = {"t": "violation", "p": "Fault Tolerance", "file": "a.py", "line": 10}
    row.update(over)
    return row


class TestSuppressionMatcher:
    def test_empty_matcher_is_inactive_and_suppresses_nothing(self):
        m = SuppressionMatcher(dimension="reliability")
        assert not m.active
        assert not m.is_suppressed(_evidence())

    def test_dismissed_matches_req_file_line(self):
        m = SuppressionMatcher(
            dimension="reliability",
            dismissed=frozenset({("R-FT-1", "a.py", 10)}),
        )
        assert m.active
        assert m.is_suppressed(_evidence(req="R-FT-1"))
        assert not m.is_suppressed(_evidence(req="R-FT-1", line=11))
        assert not m.is_suppressed(_evidence(req="R-FT-2"))

    def test_dismissed_falls_back_to_p_when_row_has_no_req(self):
        m = SuppressionMatcher(
            dimension="reliability",
            dismissed=frozenset({("R-FT-1", "a.py", 10)}),
        )
        assert m.is_suppressed(_evidence(p="R-FT-1"))

    def test_dismissed_missing_line_coerces_to_zero(self):
        m = SuppressionMatcher(
            dimension="reliability",
            dismissed=frozenset({("R-FT-1", "a.py", 0)}),
        )
        row = _evidence(req="R-FT-1")
        del row["line"]
        assert m.is_suppressed(row)

    def test_deleted_matches_dimension_principle_file_ignoring_line(self):
        m = SuppressionMatcher(
            dimension="reliability",
            deleted=frozenset({("reliability", "Fault Tolerance", "a.py")}),
        )
        assert m.is_suppressed(_evidence())
        assert m.is_suppressed(_evidence(line=999))
        assert not m.is_suppressed(_evidence(file="b.py"))

    def test_deleted_key_uses_the_mapped_principle_not_the_req_id(self):
        """Evidence rows carry req IDs; the delete store carries principle names."""
        m = SuppressionMatcher(
            dimension="reliability",
            deleted=frozenset({("reliability", "Fault Tolerance", "a.py")}),
            req_to_principle={"R-FT-1": "Fault Tolerance"},
        )
        assert m.is_suppressed(_evidence(p="R-FT-1"))

    def test_deleted_does_not_match_a_different_dimension(self):
        m = SuppressionMatcher(
            dimension="security",
            deleted=frozenset({("reliability", "Fault Tolerance", "a.py")}),
        )
        assert not m.is_suppressed(_evidence())

    def test_compliance_rows_are_never_suppressed(self):
        m = SuppressionMatcher(
            dimension="reliability",
            dismissed=frozenset({("R-FT-1", "a.py", 10)}),
            deleted=frozenset({("reliability", "Fault Tolerance", "a.py")}),
        )
        assert not m.is_suppressed(_evidence(t="compliance", req="R-FT-1"))


class TestLoadReqToPrinciple:
    """evaluators_dir is required (CLEA-DEP-07, row 9184): this reader never
    falls back to global config -- callers resolve the production default."""

    def test_evaluators_dir_is_required(self):
        with pytest.raises(TypeError):
            load_req_to_principle("reliability")  # missing evaluators_dir

    def test_reads_the_requirement_to_principle_map(self, tmp_path):
        (tmp_path / "reliability.json").write_text(json.dumps({
            "principles": [{"name": "Fault Tolerance", "requirements": [{"id": "R-FT-1"}]}],
        }))
        assert load_req_to_principle("reliability", tmp_path) == {"R-FT-1": "Fault Tolerance"}

    def test_missing_dir_returns_empty_map(self, tmp_path):
        assert load_req_to_principle("reliability", tmp_path / "nope") == {}


class TestBuildMatcherResolvesEvaluatorsDir:
    def test_explicit_evaluators_dir_feeds_req_to_principle(self, tmp_path):
        (tmp_path / "reliability.json").write_text(json.dumps({
            "principles": [{"name": "Fault Tolerance", "requirements": [{"id": "R-FT-1"}]}],
        }))
        m = build_matcher(
            "reliability", dismissed=frozenset({("R-FT-1", "a.py", 1)}), deleted=frozenset(),
            evaluators_dir=tmp_path,
        )
        assert m.req_to_principle == {"R-FT-1": "Fault Tolerance"}

    def test_default_evaluators_dir_used_when_none_passed(self, monkeypatch, tmp_path):
        """None still resolves to the production default at call time --
        the call-time-default seam moved from load_req_to_principle up into
        build_matcher, not dropped."""
        import quodeq.services.suppression as suppression_mod

        monkeypatch.setattr(suppression_mod, "default_paths", lambda: type(
            "P", (), {"evaluators_dir": tmp_path},
        )())
        (tmp_path / "reliability.json").write_text(json.dumps({
            "principles": [{"name": "Fault Tolerance", "requirements": [{"id": "R-FT-1"}]}],
        }))
        m = build_matcher(
            "reliability", dismissed=frozenset({("R-FT-1", "a.py", 1)}), deleted=frozenset(),
        )
        assert m.req_to_principle == {"R-FT-1": "Fault Tolerance"}


class TestMatcherFor:
    def test_reads_dismissed_and_deleted_from_the_project_dir(self, tmp_path):
        (tmp_path / "deleted.json").write_text(json.dumps([
            {"dimension": "reliability", "principle": "Fault Tolerance", "file": "a.py"},
        ]))
        m = matcher_for(tmp_path, "reliability", evaluators_dir=tmp_path / "nope")
        assert m.active
        assert m.is_suppressed(_evidence())

    def test_inactive_when_the_project_has_no_suppressions(self, tmp_path):
        assert not matcher_for(tmp_path, "reliability", evaluators_dir=tmp_path / "nope").active

    def test_picks_up_a_delete_written_after_the_first_call(self, tmp_path):
        """Polled every second during a scan -- a stale memo would freeze counts."""
        assert not matcher_for(tmp_path, "reliability", evaluators_dir=tmp_path / "nope").active
        (tmp_path / "deleted.json").write_text(json.dumps([
            {"dimension": "reliability", "principle": "Fault Tolerance", "file": "a.py"},
        ]))
        assert matcher_for(tmp_path, "reliability", evaluators_dir=tmp_path / "nope").active


class TestParityWithTheDashboardParsePath:
    """The live tally and the scored report must exclude the same rows."""

    @pytest.fixture
    def project(self, tmp_path):
        (tmp_path / "deleted.json").write_text(json.dumps([
            {"dimension": "reliability", "principle": "Fault Tolerance", "file": "a.py"},
        ]))
        return tmp_path

    def test_tally_and_parse_agree_on_which_rows_survive(self, project, tmp_path):
        from quodeq.analysis.subagents.jsonl_utils import tally_unique_findings
        from quodeq.services._violations_jsonl import _parse_jsonl_findings
        from quodeq.services.deleted import deleted_keys

        rows = [
            _evidence(file="a.py", line=1),          # deleted
            _evidence(file="a.py", line=2),          # deleted
            _evidence(file="b.py", line=3),          # kept
            _evidence(file="b.py", line=3),          # duplicate of the above
            _evidence(t="compliance", file="a.py", line=4),  # kept, compliance
        ]
        jsonl = tmp_path / "reliability_evidence.jsonl"
        jsonl.write_text("\n".join(json.dumps(r) for r in rows))

        m = matcher_for(project, "reliability", evaluators_dir=tmp_path / "nope")
        tally = tally_unique_findings(jsonl, suppressed=m.is_suppressed)

        parsed, compliance = _parse_jsonl_findings(
            jsonl.read_text().splitlines(), "reliability",
            keys=SuppressionKeys(frozenset(), deleted_keys(project)),
        )

        assert tally.violations == len(parsed) == 1
        assert tally.compliance == len(compliance) == 1
        assert tally.suppressed == 2
        assert tally.duplicates == 1
