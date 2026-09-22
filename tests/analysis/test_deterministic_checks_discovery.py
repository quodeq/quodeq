"""Wiring deterministic checkers into a run — discovery and fail-soft.

Split from test_deterministic_checks.py: a requirement opts into a checker
by naming it; an unknown checker name is ignored (forward compatible), and
anything that goes wrong loses only the deterministic findings, never the
run. Shared fixtures live in tests/analysis/_deterministic_checks_fixtures.py.
"""
from __future__ import annotations

from quodeq.analysis.checks.runner import deterministic_judgments
from tests.analysis._deterministic_checks_fixtures import (  # noqa: F401 -- project/compiled are pytest fixtures
    SOURCES,
    STANDARD,
    _judge,
    compiled,
    project,
)


class TestDiscovery:
    def test_a_declared_checker_runs(self, project, compiled):
        """order.py reaches flask through utils, and no inner file imports it
        directly -- so DEP-06 is violated and FRM-01 comes back clean."""
        judgments = _judge(project, compiled(STANDARD))

        assert [(j.practice_id, j.verdict, j.file) for j in judgments] == [
            ("CLEA-DEP-06", "violation", "app/domain/order.py"),
            ("CLEA-FRM-01", "compliance", "app/domain/order.py"),
        ]

    def test_a_standard_declaring_no_checks_runs_nothing(self, project, compiled):
        bare = {"principles": [{"name": "Dependency Rule",
                                "requirements": [{"id": "CLEA-DEP-06", "text": "x"}]}]}

        assert _judge(project, compiled(bare)) == []

    def test_an_unknown_checker_name_is_ignored(self, project, compiled):
        """Standards ship as data and outlive the binaries that read them."""
        future = {"principles": [{"name": "Dependency Rule", "requirements": [
            {"id": "CLEA-DEP-06", "text": "x", "check": "quantum-entanglement"}]}]}

        assert _judge(project, compiled(future)) == []

    def test_judgments_are_filtered_to_the_declaring_requirements(self, project, compiled):
        """The checker can answer FRM-01 too, but only DEP-06 asked."""
        partial = {"principles": [{"name": "Dependency Rule", "requirements": [
            {"id": "CLEA-DEP-06", "text": "x", "check": "framework-imports"}]}]}
        direct = {"principles": [{"name": "Independence from Frameworks", "requirements": [
            {"id": "CLEA-FRM-01", "text": "x", "check": "framework-imports"}]}]}

        assert [(j.practice_id, j.verdict)
                for j in _judge(project, compiled(partial))] == [
            ("CLEA-DEP-06", "violation"),
        ]
        # utils/text.py imports flask directly but is not an inner layer, so
        # FRM-01 is clean -- and the checker's DEP-06 verdict is filtered out
        # because this standard never asked for it.
        assert [(j.practice_id, j.verdict)
                for j in _judge(project, compiled(direct))] == [
            ("CLEA-FRM-01", "compliance"),
        ]

    def test_a_checker_runs_once_for_many_declaring_requirements(self, project, compiled):
        """Two requirements naming one checker must not double the findings."""
        judgments = _judge(project, compiled(STANDARD))

        assert len(judgments) == len({(j.practice_id, j.file, j.line) for j in judgments})


class TestFailSoft:
    def test_no_standard_for_the_dimension(self, project, compiled):
        assert _judge(project, compiled(STANDARD), dimension="security") == []

    def test_no_compiled_dir(self, project):
        assert deterministic_judgments(
            root=project, source_files=SOURCES, dimension="clean-architecture",
            compiled_dir=None,
        ) == []

    def test_no_source_files(self, project, compiled):
        assert deterministic_judgments(
            root=project, source_files=(), dimension="clean-architecture",
            compiled_dir=compiled(STANDARD),
        ) == []

    def test_a_checker_that_raises_does_not_take_the_run_down(
        self, project, compiled, monkeypatch,
    ):
        from quodeq.analysis.checks import registry

        def boom(_context):
            raise RuntimeError("checker exploded")

        monkeypatch.setitem(registry.CHECKERS, "framework-imports", boom)

        assert _judge(project, compiled(STANDARD)) == []
