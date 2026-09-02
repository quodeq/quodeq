"""Wiring deterministic checkers into a run — severity gates.

Split from test_deterministic_checks.py: a checker's findings go through
the same provenance/scope severity gates as everyone else. Shared
fixtures live in tests/analysis/_deterministic_checks_fixtures.py.
"""
from __future__ import annotations

import json

from quodeq.core.evidence.model import Evidence
from tests.analysis._deterministic_checks_fixtures import (  # noqa: F401 -- project/compiled are pytest fixtures
    SOURCES,
    compiled,
    project,
)


class TestSeverityGates:
    """A checker's findings go through the same severity gates as everyone else.

    The checks path is the third finding sink, after ``FindingEnricher.enrich``
    (live) and ``_write_findings`` (cache replay). It used to write straight to
    the evidence and the JSONL, so a checker declared on a gated requirement
    would land at whatever severity it assigned -- the same "code path nobody
    enumerated" shape as issue #657.

    No shipped standard declares a ``check`` on a gated requirement today, so
    these use a fake checker on ``S-AUT-3``: the point is that the wiring holds
    the moment one does.
    """

    GATED = {
        "id": "security",
        "principles": [{
            "name": "Authentication",
            "requirements": [{"id": "S-AUT-3", "text": "paths built from values",
                              "check": "fake-gated"}],
        }],
    }

    def _checker(self, monkeypatch, *, severity, reason):
        from quodeq.analysis.checks import registry
        from quodeq.core.events.models import Judgment

        def fake(_context):
            return [Judgment(
                practice_id="S-AUT-3", req="S-AUT-3", verdict="violation",
                dimension="security", file="app/utils/text.py", line=1,
                severity=severity, reason=reason, title="Path built from a value",
            )]

        monkeypatch.setitem(registry.CHECKERS, "fake-gated", fake)

    def _apply(self, project, compiled, tmp_path, *, trust_model=None):
        from quodeq.analysis.checks.runner import apply_deterministic_checks

        jsonl = tmp_path / "run" / "evidence" / "security_evidence.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=3, files_read=3, coverage_pct=100.0)
        added = apply_deterministic_checks(
            evidence, root=project, source_files=SOURCES, dimension="security",
            compiled_dir=compiled(self.GATED, "security"), jsonl_path=jsonl,
            trust_model=trust_model,
        )
        return added, evidence, jsonl

    def _violation(self, evidence):
        return evidence.principles["Authentication"].violations[0]

    def test_a_critical_naming_no_external_source_is_downgraded(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        """The provenance gate (#639) must reach a checker finding too."""
        self._checker(monkeypatch, severity="critical",
                      reason="Path is built from a caller-supplied value.")

        added, evidence, jsonl = self._apply(project, compiled, tmp_path)

        assert added == 1
        violation = self._violation(evidence)
        assert violation["severity"] == "major", "evidence drives the score"
        assert violation["provenance_downgrade"] is True

        wire = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
        assert wire["severity"] == "major", "the JSONL is what the report reads"

        events = jsonl.parent.parent / "events.jsonl"
        payload = json.loads(events.read_text(encoding="utf-8").splitlines()[0])["payload"]
        assert payload["severity"] == "major", "the SQL projection reads events.jsonl"
        assert payload["provenance_downgrade"] is True

    def test_a_critical_naming_a_real_external_source_is_left_alone(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        """The gate must not flatten a genuine critical."""
        self._checker(monkeypatch, severity="critical",
                      reason="Path is built from the request body.")

        _added, evidence, _jsonl = self._apply(project, compiled, tmp_path)

        assert self._violation(evidence)["severity"] == "critical"

    def test_a_major_out_of_the_declared_scope_is_capped(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        """The scope gate must reach a checker finding too."""
        from quodeq.context.trust_model import TrustModel

        self._checker(monkeypatch, severity="major",
                      reason="Path is built from a value with no validation.")

        _added, evidence, jsonl = self._apply(
            project, compiled, tmp_path,
            trust_model=TrustModel(multi_tenant=False, network_exposure="loopback"),
        )

        assert self._violation(evidence)["severity"] == "minor"
        wire = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
        assert wire["severity"] == "minor"
        assert wire["scope_downgrade"]["rule"] == "sourceless_path"

        events = jsonl.parent.parent / "events.jsonl"
        payload = json.loads(events.read_text(encoding="utf-8").splitlines()[0])["payload"]
        assert payload["severity"] == "minor", "the SQL projection reads events.jsonl"
        assert payload["scope_downgrade"]["rule"] == "sourceless_path", (
            "_gate must carry the marker onto the Judgment too, not just the "
            "wire row -- events.jsonl is what the SQL projection and the "
            "dashboard actually read, and _persist mirrors judgments, not rows"
        )

    def test_a_conservative_trust_model_caps_nothing(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        from quodeq.context.trust_model import CONSERVATIVE

        self._checker(monkeypatch, severity="major",
                      reason="Path is built from a value with no validation.")

        _added, evidence, _jsonl = self._apply(
            project, compiled, tmp_path, trust_model=CONSERVATIVE)

        assert self._violation(evidence)["severity"] == "major"

    def test_the_gates_run_in_order_so_a_critical_can_fall_twice(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        """Provenance first (critical -> major), then scope (major -> minor).

        Reversing the order loses the second hop entirely: apply_scope_gate
        only ever looks at ``major``, so it would see a ``critical`` and pass.
        """
        from quodeq.context.trust_model import TrustModel

        self._checker(monkeypatch, severity="critical",
                      reason="Path is built from a value with no validation.")

        _added, evidence, _jsonl = self._apply(
            project, compiled, tmp_path,
            trust_model=TrustModel(multi_tenant=False, network_exposure="loopback"),
        )

        violation = self._violation(evidence)
        assert violation["severity"] == "minor"
        assert violation["provenance_downgrade"] is True

    def test_a_compliance_is_never_touched(
        self, project, compiled, tmp_path, monkeypatch,
    ):
        from quodeq.analysis.checks import registry
        from quodeq.analysis.checks.runner import deterministic_judgments
        from quodeq.core.events.models import Judgment

        def fake(_context):
            return [Judgment(practice_id="S-AUT-3", req="S-AUT-3",
                             verdict="compliance", dimension="security",
                             file="app/utils/text.py", line=1, severity="critical",
                             reason="No path is built from a value here.")]

        monkeypatch.setitem(registry.CHECKERS, "fake-gated", fake)
        judgments = deterministic_judgments(
            root=project, source_files=SOURCES, dimension="security",
            compiled_dir=compiled(self.GATED, "security"))

        assert [j.severity for j in judgments] == ["critical"]
