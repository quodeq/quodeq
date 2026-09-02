"""Wiring deterministic checkers into a run — trust-model resolution and the
bundled clean-architecture standard.

Split from test_deterministic_checks.py (further split out of the "gates"
topic to stay under the file-size cap). Shared fixtures live in
tests/analysis/_deterministic_checks_fixtures.py.
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


class TestTrustModelWiring:
    """``apply_checks_for_run`` resolves the trust model the way the cache path does."""

    def _config(self, project, compiled_dir, tmp_path):
        from types import SimpleNamespace

        from quodeq.analysis._types import RunConfig

        work_dir = tmp_path / "run" / "evidence"
        work_dir.mkdir(parents=True, exist_ok=True)
        return RunConfig(
            src=project, language="python", standards_dir=compiled_dir.parent,
            work_dir=work_dir, manifest=SimpleNamespace(source_files=list(SOURCES)),
        )

    def test_the_trust_model_is_resolved_once_per_dimension(
        self, project, compiled, tmp_path,
    ):
        """Resolution reads the profile and walks the manifests; doing it per
        finding would repeat that work for every judgment."""
        from unittest.mock import patch

        from quodeq.analysis.checks.runner import apply_checks_for_run
        from quodeq.context.trust_model import CONSERVATIVE

        config = self._config(project, compiled(STANDARD), tmp_path)
        evidence = Evidence(repository="r", language="python", date="d",
                            source_file_count=3, files_read=3, coverage_pct=100.0)

        with patch("quodeq.analysis.checks.runner.resolve_trust_model",
                   return_value=CONSERVATIVE) as resolve:
            added = apply_checks_for_run(config, "clean-architecture", evidence)

        assert added == 2, "two findings"
        assert resolve.call_count == 1
        assert resolve.call_args.args[0] == project


class TestBundledStandard:
    def test_clean_architecture_declares_the_framework_checker(self):
        """The shipped standard is what makes any of this run for real users."""
        from quodeq.config.paths import default_paths

        compiled = default_paths().standards_dir / "compiled" / "clean-architecture.json"
        data = json.loads(compiled.read_text(encoding="utf-8"))
        checks = {
            req["id"]: req.get("check")
            for principle in data["principles"] for req in principle["requirements"]
        }

        assert checks["CLEA-FRM-01"] == "framework-imports"
        assert checks["CLEA-DEP-06"] == "framework-imports"
        assert checks["CLEA-DEP-02"] == "entity-imports"
        assert checks["CLEA-DEP-07"] == "config-reads"
        assert checks["CLEA-DEP-01"] is None, "the inward rule needs a declared layer map first"

    def test_every_declared_checker_name_exists(self):
        """A standard naming a checker we do not ship is silently inert."""
        import json as _json

        from quodeq.analysis.checks.registry import CHECKERS
        from quodeq.config.paths import default_paths

        compiled_dir = default_paths().standards_dir / "compiled"
        declared = set()
        for path in compiled_dir.glob("*.json"):
            data = _json.loads(path.read_text(encoding="utf-8"))
            for principle in data.get("principles", []):
                for req in principle.get("requirements", []):
                    if req.get("check"):
                        declared.add(req["check"])

        assert declared <= set(CHECKERS), f"unknown: {declared - set(CHECKERS)}"

    def test_the_context_parses_the_tree_once_per_context(self, project):
        """Three checkers over one context must not be three walks of the tree."""
        from quodeq.analysis.checks.registry import CheckContext
        from quodeq.data.fs.import_graph import build_import_graph
        from quodeq.data.fs.symbol_uses import build_symbol_uses

        context = CheckContext(root=project, source_files=SOURCES,
                               dimension="clean-architecture",
                               graph_builder=build_import_graph,
                               symbol_uses_builder=build_symbol_uses)

        assert context.graph() is context.graph()
        assert context.config_symbol_uses() is context.config_symbol_uses()

    def test_the_context_uses_the_injected_graph_builder(self, tmp_path):
        """An in-memory graph can be supplied without touching the filesystem."""
        from quodeq.analysis.checks.registry import CheckContext
        from quodeq.core.checks.model import ImportGraph

        fake_graph = ImportGraph(first_party=frozenset({"app"}))
        calls: list[tuple] = []

        def fake_builder(root, paths):
            calls.append((root, tuple(paths)))
            return fake_graph

        context = CheckContext(root=tmp_path, source_files=("app/x.py",),
                               dimension="clean-architecture",
                               graph_builder=fake_builder)

        assert context.graph() is fake_graph
        assert context.graph() is fake_graph  # memoised: builder ran once
        assert len(calls) == 1

    def test_the_context_without_a_builder_refuses_instead_of_reading_disk(self, tmp_path):
        """No builder injected -> a clear error, never a hidden fs fallback."""
        import pytest

        from quodeq.analysis.checks.registry import CheckContext

        context = CheckContext(root=tmp_path, source_files=("app/x.py",),
                               dimension="clean-architecture")

        with pytest.raises(RuntimeError, match="graph_builder"):
            context.graph()
        with pytest.raises(RuntimeError, match="symbol_uses_builder"):
            context.config_symbol_uses()
