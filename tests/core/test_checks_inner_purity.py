"""Two more requirements the per-file scan could never answer.

* **CLEA-DEP-02** -- "Entities must not import from use case or adapter layers".
  Judged on the *module name* being imported rather than on resolving it to a
  file, so it still works when the target's source is not in the file list.
* **CLEA-DEP-07** -- "Configuration and environment variables are not read in
  inner layers". ``os.environ`` reaches the inner layer under a dozen spellings
  (aliased import, ``from os import environ``, a config package); each is
  invisible to a text search and obvious to an AST.

Both follow the pattern set by the framework checker: a layer we cannot name
is a layer we do not judge, and a check that ran clean says so once.
"""
from __future__ import annotations

from quodeq.core.checks.config_reads import check_config_reads
from quodeq.core.checks.entity_imports import check_entity_imports
from quodeq.core.checks.model import ImportEdge, ImportGraph, SymbolUse


def _graph(*edges: tuple[str, int, str]) -> ImportGraph:
    return ImportGraph(
        edges=tuple(ImportEdge(file=f, line=n, module=m) for f, n, m in edges),
        first_party=frozenset({"app"}),
    )


def _entities(graph: ImportGraph) -> list:
    return check_entity_imports(graph, dimension="clean-architecture")


def _violations(judgments: list) -> list:
    return [j for j in judgments if j.verdict == "violation"]


class TestEntitiesDoNotImportOutward:
    def test_an_entity_importing_an_adapter_is_a_violation(self):
        judgments = _violations(_entities(_graph(
            ("app/domain/order.py", 4, "app.adapters.sql_repo"),
        )))

        assert len(judgments) == 1
        j = judgments[0]
        assert j.practice_id == "CLEA-DEP-02"
        assert j.file == "app/domain/order.py"
        assert j.line == 4
        assert "app.adapters.sql_repo" in j.reason

    def test_every_conventional_outer_layer_counts(self):
        for module in (
            "app.adapters.x", "app.infrastructure.x", "app.controllers.x",
            "app.presenters.x", "app.gateways.x", "app.repositories.x",
            "app.api.x", "app.web.x", "app.ui.x", "app.persistence.x",
        ):
            judgments = _violations(_entities(_graph(("app/domain/o.py", 1, module))))
            assert len(judgments) == 1, module

    def test_entities_may_import_other_entities(self):
        assert _violations(_entities(_graph(
            ("app/domain/order.py", 1, "app.domain.money"),
            ("app/entities/user.py", 1, "app.entities.role"),
        ))) == []

    def test_third_party_and_stdlib_imports_are_not_outer_layers(self):
        """``requests`` is a framework question (FRM-01), not a layering one."""
        assert _violations(_entities(_graph(
            ("app/domain/order.py", 1, "decimal"),
            ("app/domain/order.py", 2, "requests"),
        ))) == []

    def test_matching_is_on_whole_segments(self):
        assert _violations(_entities(_graph(
            ("app/domain/order.py", 1, "app.website.render"),
            ("app/domain/order.py", 2, "app.apiary.x"),
        ))) == []

    def test_a_use_case_layer_importing_an_adapter_is_not_this_requirement(self):
        """DEP-02 is about entities. Use cases reaching adapters is DEP-01."""
        assert _violations(_entities(_graph(
            ("app/usecases/place_order.py", 1, "app.adapters.sql_repo"),
        ))) == []

    def test_one_violation_per_target_module_not_per_import_line(self):
        judgments = _violations(_entities(_graph(
            ("app/domain/order.py", 3, "app.adapters.sql"),
            ("app/domain/order.py", 4, "app.adapters.sql"),
        )))

        assert len(judgments) == 1
        assert judgments[0].line == 3

    def test_a_clean_entity_layer_reports_itself_clean(self):
        judgments = _entities(_graph(("app/domain/order.py", 1, "decimal")))

        assert [(j.practice_id, j.verdict) for j in judgments] == [
            ("CLEA-DEP-02", "compliance"),
        ]

    def test_no_entity_layer_means_no_judgment_at_all(self):
        """``core/`` and ``domain/`` we can name; ``lib/`` we cannot."""
        assert _entities(_graph(("lib/order.py", 1, "app.adapters.sql"))) == []

    def test_core_counts_as_an_entity_layer(self):
        judgments = _violations(_entities(_graph(
            ("src/pkg/core/model.py", 1, "app.infrastructure.db"),
        )))

        assert [j.file for j in judgments] == ["src/pkg/core/model.py"]


def _config(graph: ImportGraph, *uses: tuple[str, int, str]) -> list:
    return check_config_reads(
        graph,
        tuple(SymbolUse(file=f, line=n, symbol=s) for f, n, s in uses),
        dimension="clean-architecture",
    )


class TestInnerLayersDoNotReadConfig:
    def test_reading_os_environ_in_an_inner_layer_is_a_violation(self):
        judgments = _violations(_config(
            _graph(("app/domain/order.py", 1, "os")),
            ("app/domain/order.py", 7, "os.environ"),
        ))

        assert len(judgments) == 1
        j = judgments[0]
        assert j.practice_id == "CLEA-DEP-07"
        assert j.line == 7
        assert "os.environ" in j.reason

    def test_importing_a_config_package_is_a_violation(self):
        judgments = _violations(_config(
            _graph(("app/domain/order.py", 2, "dotenv")),
        ))

        assert [j.practice_id for j in judgments] == ["CLEA-DEP-07"]
        assert "dotenv" in judgments[0].reason

    def test_outer_layers_may_read_configuration(self):
        assert _violations(_config(
            _graph(("app/api/routes.py", 1, "os"), ("app/domain/order.py", 1, "decimal")),
            ("app/api/routes.py", 3, "os.environ"),
        )) == []

    def test_one_violation_per_file_and_source(self):
        judgments = _violations(_config(
            _graph(("app/domain/order.py", 1, "os")),
            ("app/domain/order.py", 7, "os.environ"),
            ("app/domain/order.py", 9, "os.environ"),
            ("app/domain/order.py", 11, "os.getenv"),
        ))

        assert len(judgments) == 2
        assert [j.line for j in judgments] == [7, 11]

    def test_a_clean_inner_layer_reports_itself_clean(self):
        judgments = _config(_graph(("app/domain/order.py", 1, "decimal")))

        assert [(j.practice_id, j.verdict) for j in judgments] == [
            ("CLEA-DEP-07", "compliance"),
        ]

    def test_no_inner_layer_means_no_judgment_at_all(self):
        assert _config(
            _graph(("main.py", 1, "os")), ("main.py", 3, "os.environ"),
        ) == []

    def test_a_use_case_layer_counts_as_inner(self):
        """Unlike DEP-02, this requirement covers every inner layer."""
        judgments = _violations(_config(
            _graph(("app/usecases/place_order.py", 1, "os")),
            ("app/usecases/place_order.py", 4, "os.getenv"),
        ))

        assert [j.file for j in judgments] == ["app/usecases/place_order.py"]


class TestSharedShape:
    def test_both_checkers_are_deterministic_and_sorted(self):
        graph = _graph(
            ("app/domain/b.py", 1, "app.adapters.x"),
            ("app/domain/a.py", 1, "app.web.y"),
        )

        first = [(j.file, j.line) for j in _entities(graph)]
        assert first == sorted(first) == [(j.file, j.line) for j in _entities(graph)]

    def test_findings_carry_the_dimension_severity_and_full_confidence(self):
        j = _violations(_entities(_graph(("app/domain/o.py", 1, "app.api.x"))))[0]

        assert j.dimension == "clean-architecture"
        assert j.severity == "major"
        assert j.confidence == 100

    def test_empty_inputs(self):
        assert _entities(ImportGraph()) == []
        assert check_config_reads(ImportGraph(), (), dimension="d") == []
