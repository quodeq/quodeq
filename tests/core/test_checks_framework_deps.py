"""Framework dependencies reaching the inner layers -- CLEA-FRM-01, CLEA-DEP-06.

Twenty of the clean-architecture standard's fifty-two requirements have never
produced a single judgment, because they are properties of the import graph
and a per-file LLM pass cannot see a graph. CLEA-DEP-06 is the clearest case:
"if entity A imports utility B, and utility B imports Flask, then A has a
transitive framework dependency". Reading A tells you nothing about Flask.

Two requirements, one traversal:

* **CLEA-FRM-01** (direct) -- an inner-layer file imports a framework itself.
* **CLEA-DEP-06** (transitive) -- an inner-layer file reaches a framework
  *through a first-party module that is not itself inner-layer*.

The "not itself inner-layer" clause is what keeps this from avalanching. If
the path runs through another inner file, that file already carries its own
FRM-01 violation; re-reporting the same fact at every downstream importer
turns one defect into fifty findings and buries the fix site.
"""
from __future__ import annotations

from quodeq.core.checks.framework_deps import check_framework_dependencies
from quodeq.core.checks.model import ImportEdge, ImportGraph

FRAMEWORKS = frozenset({"flask", "pydantic", "django"})


def _graph(*edges: tuple[str, int, str]) -> ImportGraph:
    return ImportGraph(
        edges=tuple(ImportEdge(file=f, line=n, module=m) for f, n, m in edges),
        first_party=frozenset({"app"}),
    )


def _run(graph: ImportGraph) -> list:
    return check_framework_dependencies(
        graph, framework_packages=FRAMEWORKS, dimension="clean-architecture",
    )


def _violations(graph: ImportGraph) -> list:
    """Only the violations -- a clean requirement also reports itself clean."""
    return [j for j in _run(graph) if j.verdict == "violation"]


class TestDirectFrameworkImports:
    def test_inner_file_importing_a_framework_is_a_violation(self):
        judgments = _violations(_graph(("app/domain/order.py", 3, "flask")))

        assert len(judgments) == 1
        j = judgments[0]
        assert j.practice_id == "CLEA-FRM-01"
        assert j.req == "CLEA-FRM-01"
        assert j.file == "app/domain/order.py"
        assert j.line == 3
        assert "flask" in j.reason

    def test_submodule_import_resolves_to_its_top_level_package(self):
        judgments = _violations(_graph(("app/domain/order.py", 3, "pydantic.fields")))

        assert [j.practice_id for j in judgments] == ["CLEA-FRM-01"]

    def test_outer_layer_files_may_import_frameworks_freely(self):
        assert _violations(_graph(("app/api/routes.py", 1, "flask"))) == []

    def test_non_framework_imports_are_ignored(self):
        assert _violations(_graph(("app/domain/order.py", 1, "decimal"))) == []

    def test_one_violation_per_file_and_package_not_per_import(self):
        """Ten `from flask import x` lines are one defect, not ten findings."""
        judgments = _violations(_graph(
            ("app/domain/order.py", 3, "flask"),
            ("app/domain/order.py", 4, "flask.helpers"),
            ("app/domain/order.py", 5, "flask"),
        ))

        assert len(judgments) == 1
        assert judgments[0].line == 3, "report the first occurrence"

    def test_distinct_packages_are_distinct_findings(self):
        judgments = _violations(_graph(
            ("app/domain/order.py", 3, "flask"),
            ("app/domain/order.py", 4, "django"),
        ))

        assert len(judgments) == 2


class TestTransitiveFrameworkDependencies:
    def test_inner_reaches_a_framework_through_an_outer_utility(self):
        """The standard's own example: A -> B -> Flask, where B is a utility."""
        judgments = _violations(_graph(
            ("app/domain/order.py", 2, "app.utils.text"),
            ("app/utils/text.py", 1, "flask"),
        ))

        assert len(judgments) == 1
        j = judgments[0]
        assert j.practice_id == "CLEA-DEP-06"
        assert j.file == "app/domain/order.py"
        assert j.line == 2, "report at the import that pulls the dependency in"
        assert "flask" in j.reason
        assert "app.utils.text" in j.reason, "the reason must name the path"

    def test_a_path_through_another_inner_file_is_not_re_reported(self):
        """Collapse the cascade: the inner file that imports the framework
        already carries FRM-01, so its importers add nothing but noise."""
        judgments = _violations(_graph(
            ("app/domain/order.py", 2, "app.domain.money"),
            ("app/domain/money.py", 1, "pydantic"),
        ))

        assert [j.practice_id for j in judgments] == ["CLEA-FRM-01"]
        assert judgments[0].file == "app/domain/money.py"

    def test_multi_hop_paths_through_outer_modules_resolve(self):
        judgments = _violations(_graph(
            ("app/domain/order.py", 2, "app.utils.a"),
            ("app/utils/a.py", 1, "app.utils.b"),
            ("app/utils/b.py", 1, "django"),
        ))

        assert [(j.practice_id, j.file) for j in judgments] == [
            ("CLEA-DEP-06", "app/domain/order.py"),
        ]

    def test_direct_wins_over_transitive_for_the_same_package(self):
        """Don't bill one file twice for one package."""
        judgments = _violations(_graph(
            ("app/domain/order.py", 2, "flask"),
            ("app/domain/order.py", 3, "app.utils.text"),
            ("app/utils/text.py", 1, "flask"),
        ))

        assert [j.practice_id for j in judgments] == ["CLEA-FRM-01"]

    def test_import_cycles_terminate(self):
        judgments = _violations(_graph(
            ("app/domain/order.py", 2, "app.utils.a"),
            ("app/utils/a.py", 1, "app.utils.b"),
            ("app/utils/b.py", 1, "app.utils.a"),
        ))

        assert judgments == []

    def test_third_party_modules_are_not_traversed(self):
        """We can only see first-party source; a non-first-party hop is opaque."""
        assert _violations(_graph(
            ("app/domain/order.py", 2, "somelib.helpers"),
            ("app/utils/text.py", 1, "flask"),
        )) == []


class TestCleanProjectsAreMeasured:
    """A requirement nobody ever judges is not "passing", it is unmeasured.

    These two requirements sat at zero judgments for the whole life of the
    standard. Emitting violations alone would keep them there for every clean
    project -- so a check that ran and found nothing says so, once, with the
    scope it covered.
    """

    def test_a_clean_inner_layer_yields_one_compliance_per_requirement(self):
        judgments = _run(_graph(("app/domain/order.py", 1, "decimal")))

        assert [(j.practice_id, j.verdict) for j in judgments] == [
            ("CLEA-DEP-06", "compliance"), ("CLEA-FRM-01", "compliance"),
        ]

    def test_the_compliance_states_what_was_checked(self):
        judgments = _run(_graph(
            ("app/domain/order.py", 1, "decimal"),
            ("app/entities/user.py", 1, "typing"),
        ))

        assert all("2 inner-layer file" in j.reason for j in judgments)

    def test_a_violated_requirement_gets_no_compliance(self):
        """Only the requirement that came back clean is reported clean."""
        judgments = _run(_graph(("app/domain/order.py", 3, "flask")))

        assert [(j.practice_id, j.verdict) for j in judgments] == [
            ("CLEA-DEP-06", "compliance"), ("CLEA-FRM-01", "violation"),
        ]

    def test_the_compliance_is_anchored_to_a_stable_file(self):
        """Same project, same anchor -- otherwise dismissing it never sticks."""
        graph = _graph(("app/entities/user.py", 1, "typing"),
                       ("app/domain/order.py", 1, "decimal"))

        anchors = {j.file for j in _run(graph)}

        assert anchors == {"app/domain/order.py"}, "first inner file, sorted"

    def test_an_unlayered_project_is_not_reported_clean(self):
        """Nothing was checked, so there is nothing to certify."""
        assert _run(_graph(("main.py", 1, "decimal"))) == []


class TestFailSoft:
    def test_no_inner_layer_yields_no_findings(self):
        """An unlayered project is not judged, in either direction."""
        assert _run(_graph(("main.py", 1, "flask"), ("utils.py", 1, "django"))) == []

    def test_empty_graph(self):
        assert _run(ImportGraph()) == []

    def test_no_framework_list_yields_no_findings(self):
        assert check_framework_dependencies(
            _graph(("app/domain/order.py", 1, "flask")),
            framework_packages=frozenset(), dimension="clean-architecture",
        ) == []


class TestJudgmentShape:
    def test_findings_carry_the_dimension_and_a_severity(self):
        j = _violations(_graph(("app/domain/order.py", 3, "flask")))[0]

        assert j.dimension == "clean-architecture"
        assert j.severity == "major"
        assert j.confidence == 100, "a graph fact is not a guess"

    def test_output_is_deterministic(self):
        graph = _graph(
            ("app/domain/b.py", 1, "django"),
            ("app/domain/a.py", 1, "flask"),
            ("app/entities/c.py", 1, "pydantic"),
        )

        first = [(j.file, j.practice_id) for j in _run(graph)]
        second = [(j.file, j.practice_id) for j in _run(graph)]

        assert first == second == sorted(first)
