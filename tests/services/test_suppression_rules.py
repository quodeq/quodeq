"""Pattern-level suppressions: encode an ADR once instead of per line number.

Dismissals are keyed ``(req, file, line)``. Every refactor that shifts a line
re-surfaces a finding the team already decided is acceptable — this session
alone paid ~13 re-dismissals for patterns covered by the WS1 lean-architecture
ADR. A rule matches by requirement + file glob, so the decision survives the
code moving.
"""
from __future__ import annotations

import json

import pytest

from quodeq.core.types.suppression_rule import SuppressionRule
from quodeq.services.suppression_keys import is_dismissed, matches_suppression_rule


class TestMatchesSuppressionRule:
    def test_matches_req_and_file_glob(self):
        rules = (SuppressionRule(req="CLEA-DEP-01", file="src/quodeq/services/*", reason="WS1"),)
        assert matches_suppression_rule(rules, "CLEA-DEP-01", "src/quodeq/services/dismissed.py")
        assert not matches_suppression_rule(rules, "CLEA-DEP-01", "src/quodeq/api/routes.py")
        assert not matches_suppression_rule(rules, "CLEA-SEP-03", "src/quodeq/services/dismissed.py")

    def test_req_glob(self):
        rules = (SuppressionRule(req="CLEA-DEP-*", file="src/quodeq/services/*", reason="r"),)
        assert matches_suppression_rule(rules, "CLEA-DEP-05", "src/quodeq/services/a.py")
        assert not matches_suppression_rule(rules, "CLEA-SEP-01", "src/quodeq/services/a.py")

    def test_recursive_file_glob_spans_directories(self):
        rules = (SuppressionRule(req="*", file="src/quodeq/ui/**", reason="SPA adapters"),)
        assert matches_suppression_rule(rules, "CLEA-SEP-03", "src/quodeq/ui/src/hooks/useX.js")

    def test_empty_inputs_never_match(self):
        rules = (SuppressionRule(req="*", file="*", reason="r"),)
        assert not matches_suppression_rule((), "CLEA-DEP-01", "a.py")
        assert not matches_suppression_rule(rules, "", "a.py")
        assert not matches_suppression_rule(rules, "CLEA-DEP-01", "")

    def test_any_matching_rule_wins(self):
        rules = (
            SuppressionRule(req="X-1", file="a.py", reason="one"),
            SuppressionRule(req="Y-2", file="b.py", reason="two"),
        )
        assert matches_suppression_rule(rules, "Y-2", "b.py")


class TestIsDismissedHonoursRules:
    def test_rule_suppresses_without_an_exact_key(self):
        rules = (SuppressionRule(req="CLEA-DEP-01", file="src/quodeq/services/*", reason="WS1"),)
        assert is_dismissed(
            set(), req="CLEA-DEP-01", file="src/quodeq/services/x.py", line=42, rules=rules,
        )

    def test_rule_survives_a_line_shift(self):
        """The whole point: the same finding at a new line stays suppressed."""
        rules = (SuppressionRule(req="CLEA-DEP-01", file="src/quodeq/services/x.py", reason="WS1"),)
        for line in (10, 11, 9999):
            assert is_dismissed(set(), req="CLEA-DEP-01", file="src/quodeq/services/x.py",
                                line=line, rules=rules)

    def test_exact_keys_still_work_with_no_rules(self):
        keys = {("R1", "a.py", 1)}
        assert is_dismissed(keys, req="R1", file="a.py", line=1)
        assert not is_dismissed(keys, req="R1", file="a.py", line=2)

    def test_principle_fallback_applies_to_rules_too(self):
        """A no-req finding matches on its principle, mirroring the key path."""
        rules = (SuppressionRule(req="Independence", file="a.py", reason="r"),)
        assert is_dismissed(set(), req=None, principle="Independence", file="a.py",
                            line=3, rules=rules)


class TestLoadSuppressionRules:
    def test_reads_rules_from_disk(self, tmp_path):
        from quodeq.data.fs.suppression_rules import load_suppression_rules

        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "version": 1,
            "rules": [{"req": "CLEA-DEP-01", "file": "src/quodeq/services/*", "reason": "WS1"}],
        }), encoding="utf-8")

        rules = load_suppression_rules(tmp_path)

        assert len(rules) == 1
        assert rules[0].req == "CLEA-DEP-01"
        assert rules[0].reason == "WS1"

    def test_absent_or_malformed_yields_no_rules(self, tmp_path):
        from quodeq.data.fs.suppression_rules import load_suppression_rules

        assert load_suppression_rules(tmp_path) == ()
        (tmp_path / "suppression_rules.json").write_text("{nope", encoding="utf-8")
        assert load_suppression_rules(tmp_path) == ()

    def test_deeply_nested_file_yields_no_rules(self, tmp_path, deeply_nested_json):
        """"Malformed" has to mean every parse failure, not a chosen trio.

        Deeply nested JSON overflows the C decoder's call stack and raises
        RecursionError -- a RuntimeError subclass, so the narrow
        (OSError, ValueError, UnicodeDecodeError) catch let it escape and fail
        the scoring path that loads this file on every rescore.
        """
        from quodeq.data.fs.suppression_rules import load_suppression_rules

        (tmp_path / "suppression_rules.json").write_text(
            deeply_nested_json, encoding="utf-8")

        assert load_suppression_rules(tmp_path) == ()

    def test_entries_missing_a_required_field_are_skipped(self, tmp_path):
        """A half-written rule must not silently suppress everything."""
        from quodeq.data.fs.suppression_rules import load_suppression_rules

        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "rules": [
                {"file": "a.py", "reason": "no req"},
                {"req": "X-1", "reason": "no file"},
                {"req": "X-2", "file": "b.py", "reason": "complete"},
                "not-a-dict",
            ],
        }), encoding="utf-8")

        rules = load_suppression_rules(tmp_path)

        assert [r.req for r in rules] == ["X-2"]

    def test_a_rule_requires_a_reason(self, tmp_path):
        """Reasons are the point: an unexplained blanket rule is rejected."""
        from quodeq.data.fs.suppression_rules import load_suppression_rules

        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "rules": [{"req": "*", "file": "*"}],
        }), encoding="utf-8")

        assert load_suppression_rules(tmp_path) == ()


def test_suppression_rule_is_frozen():
    rule = SuppressionRule(req="X", file="a.py", reason="r")
    with pytest.raises(Exception):
        rule.req = "Y"


class TestRulesParticipateInInvalidation:
    """A rule change must invalidate cached scores.

    The cache version is a content hash of the suppression state. If rules
    were left out, adding one would hide findings while the cache kept
    serving the pre-rule payload — the stale-row failure class from the
    2026-07-29 incident.
    """

    def test_adding_a_rule_changes_the_cache_version(self, tmp_path):
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.services.score_cache import score_cache_version

        before = score_cache_version(tmp_path, DEFAULT_PARAMS)
        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "rules": [{"req": "X-1", "file": "a.py", "reason": "accepted"}],
        }), encoding="utf-8")
        after = score_cache_version(tmp_path, DEFAULT_PARAMS)

        assert before != after

    def test_editing_a_rule_changes_the_version_too(self, tmp_path):
        from quodeq.core.scoring.params import DEFAULT_PARAMS
        from quodeq.services.score_cache import score_cache_version

        path = tmp_path / "suppression_rules.json"
        path.write_text(json.dumps({"rules": [
            {"req": "X-1", "file": "a.py", "reason": "accepted"}]}), encoding="utf-8")
        before = score_cache_version(tmp_path, DEFAULT_PARAMS)
        path.write_text(json.dumps({"rules": [
            {"req": "X-1", "file": "b.py", "reason": "accepted"}]}), encoding="utf-8")

        assert score_cache_version(tmp_path, DEFAULT_PARAMS) != before


class TestReadPathsHonourRules:
    def test_dimension_filter_drops_a_rule_matched_violation(self, tmp_path):
        from quodeq.core.types.dimension import DimensionResult
        from quodeq.core.types.finding import Finding
        from quodeq.services.dismissed import filter_dismissed_from_dimensions

        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "rules": [{"req": "CLEA-DEP-01", "file": "src/quodeq/services/*",
                       "reason": "WS1 lean architecture"}],
        }), encoding="utf-8")
        dim = DimensionResult(
            dimension="clean-architecture",
            violations=[
                Finding(req="CLEA-DEP-01", practice_id="P1",
                        file="src/quodeq/services/dismissed.py", line=23, severity="major"),
                Finding(req="CLEA-DEP-01", practice_id="P1",
                        file="src/quodeq/api/routes.py", line=5, severity="major"),
            ],
        )

        out = filter_dismissed_from_dimensions([dim], tmp_path)

        assert [v.file for v in out[0].violations] == ["src/quodeq/api/routes.py"]

    def test_matcher_suppresses_a_rule_matched_row(self, tmp_path):
        from quodeq.services.suppression import matcher_for

        (tmp_path / "suppression_rules.json").write_text(json.dumps({
            "rules": [{"req": "X-1", "file": "a.py", "reason": "accepted"}],
        }), encoding="utf-8")

        matcher = matcher_for(tmp_path, "clean-architecture")

        assert matcher.active is True
        assert matcher.is_suppressed(
            {"t": "violation", "req": "X-1", "p": "X-1", "file": "a.py", "line": 7})
        assert not matcher.is_suppressed(
            {"t": "violation", "req": "X-1", "p": "X-1", "file": "b.py", "line": 7})


class TestRulesMoveTheGrade:
    """The point of the feature: a rule must change the score, not just lists."""

    def _dim(self):
        from quodeq.core.types.dimension import DimensionResult
        from quodeq.core.types.finding import Finding
        return DimensionResult(
            dimension="clean-architecture",
            overall_score="5.0/10",
            violations=[
                Finding(req="CLEA-DEP-01", practice_id="Independence",
                        file="src/quodeq/services/a.py", line=3, severity="major"),
            ],
        )

    def test_rescore_drops_a_rule_matched_violation(self):
        from quodeq.core.types.suppression_rule import SuppressionRule
        from quodeq.services.rescore import rescore_dimensions

        rules = (SuppressionRule(req="CLEA-DEP-01", file="src/quodeq/services/*",
                                 reason="WS1"),)
        out = rescore_dimensions([self._dim()], set(), set(), rules=rules)

        assert out["dimensions"][0]["violations"] == []

    def test_without_the_rule_the_violation_survives(self):
        from quodeq.services.rescore import rescore_dimensions

        out = rescore_dimensions([self._dim()], set(), set())

        assert len(out["dimensions"][0]["violations"]) == 1

    def test_scored_run_dimensions_loads_rules_from_the_project(self, tmp_path):
        """End-to-end: the entry point reads the rules file itself."""
        from quodeq.services.scoring import ScoringDeps, scored_run_dimensions

        (tmp_path / "proj").mkdir()
        (tmp_path / "proj" / "suppression_rules.json").write_text(json.dumps({
            "rules": [{"req": "CLEA-DEP-01", "file": "src/quodeq/services/*",
                       "reason": "WS1"}],
        }), encoding="utf-8")
        dim = self._dim()
        deps = ScoringDeps(
            read_run_data=lambda root, p, r: [dim],
            dismissed_keys=lambda pd: set(),
            deleted_keys=lambda pd: set(),
        )

        out = scored_run_dimensions(tmp_path, "proj", "run-1", deps=deps)

        assert out[0].violations == [], "a project rule must reach the scoring path"
