"""Building the import graph off disk -- the only I/O a checker needs.

The checkers in ``core/checks`` are pure functions over an ``ImportGraph``.
This is where the graph comes from: parse each source file, record what it
imports, and work out which top-level packages the project owns.

Parsing is via ``ast``, not regex, because the failure mode of a regex here is
silent: a missed import is a dependency the checker reports as absent. A file
that will not parse contributes nothing rather than half a file's worth of
edges.
"""
from __future__ import annotations

from quodeq.data.fs.import_graph import build_import_graph


def _write(root, rel: str, body: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestFirstPartyDetection:
    def test_packages_are_the_topmost_dir_with_an_init(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/domain/__init__.py", "")
        _write(tmp_path, "app/domain/order.py", "import flask\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/domain/order.py"])

        assert graph.first_party == frozenset({"app"})

    def test_src_layout_is_seen_through(self, tmp_path):
        _write(tmp_path, "src/mypkg/__init__.py", "")
        _write(tmp_path, "src/mypkg/core/__init__.py", "")
        _write(tmp_path, "src/mypkg/core/x.py", "import os\n")

        graph = build_import_graph(tmp_path, [tmp_path / "src/mypkg/core/x.py"])

        assert graph.first_party == frozenset({"mypkg"}), "src/ is not a package"

    def test_a_flat_script_owns_no_package(self, tmp_path):
        _write(tmp_path, "main.py", "import flask\n")

        graph = build_import_graph(tmp_path, [tmp_path / "main.py"])

        assert graph.first_party == frozenset()


class TestEdges:
    def test_plain_and_from_imports(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/x.py", "import flask\nfrom pydantic import BaseModel\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/x.py"])

        assert {(e.module, e.line) for e in graph.edges} == {("flask", 1), ("pydantic", 2)}

    def test_paths_are_repo_relative_posix(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/sub/mod.py", "import os\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/sub/mod.py"])

        assert [e.file for e in graph.edges] == ["app/sub/mod.py"]

    def test_dotted_from_import_keeps_the_full_module(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/x.py", "from app.utils.text import slugify\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/x.py"])

        assert [e.module for e in graph.edges] == ["app.utils.text"]

    def test_relative_imports_resolve_to_absolute_modules(self, tmp_path):
        """``from . import x`` inside app/domain must become app.domain.x --
        an unresolved relative import is an edge the checker cannot follow."""
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/domain/__init__.py", "")
        _write(tmp_path, "app/domain/money.py", "")
        _write(tmp_path, "app/utils/__init__.py", "")
        _write(tmp_path, "app/utils/text.py", "")
        _write(tmp_path, "app/domain/order.py",
               "from . import money\nfrom ..utils import text\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/domain/order.py"])

        assert {e.module for e in graph.edges} == {"app.domain.money", "app.utils.text"}

    def test_an_imported_name_that_is_not_a_module_keeps_the_package(self, tmp_path):
        """``from app.utils import slugify`` imports a function, not a module."""
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/utils/__init__.py", "")
        _write(tmp_path, "app/x.py", "from app.utils import slugify\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/x.py"])

        assert [e.module for e in graph.edges] == ["app.utils"]

    def test_function_body_imports_are_edges_too(self, tmp_path):
        """A deferred import is still a dependency."""
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/x.py", "def f():\n    import flask\n    return flask\n")

        graph = build_import_graph(tmp_path, [tmp_path / "app/x.py"])

        assert [e.module for e in graph.edges] == ["flask"]


class TestFailSoft:
    def test_a_file_that_will_not_parse_contributes_nothing(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/broken.py", "def (:\n")
        _write(tmp_path, "app/ok.py", "import flask\n")

        graph = build_import_graph(
            tmp_path, [tmp_path / "app/broken.py", tmp_path / "app/ok.py"],
        )

        assert [e.file for e in graph.edges] == ["app/ok.py"]

    def test_missing_and_non_python_files_are_skipped(self, tmp_path):
        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/notes.md", "# hi\n")

        graph = build_import_graph(
            tmp_path, [tmp_path / "app/notes.md", tmp_path / "app/gone.py"],
        )

        assert graph.edges == ()

    def test_paths_outside_the_root_are_skipped(self, tmp_path):
        """A file list is not a licence to read anywhere on the disk."""
        outside = tmp_path.parent / "outside.py"
        outside.write_text("import flask\n", encoding="utf-8")
        root = tmp_path / "repo"
        _write(root, "app/__init__.py", "")

        assert build_import_graph(root, [outside]).edges == ()

    def test_empty_file_list(self, tmp_path):
        assert build_import_graph(tmp_path, []).edges == ()


class TestEndToEndWithTheChecker:
    def test_a_transitive_framework_dependency_is_found_on_disk(self, tmp_path):
        """The whole point, exercised through real files."""
        from quodeq.core.checks.framework_deps import check_framework_dependencies

        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/domain/__init__.py", "")
        _write(tmp_path, "app/domain/order.py", "from app.utils import text\n")
        _write(tmp_path, "app/utils/__init__.py", "")
        _write(tmp_path, "app/utils/text.py", "import flask\n")

        graph = build_import_graph(tmp_path, [
            tmp_path / "app/domain/order.py",
            tmp_path / "app/utils/text.py",
            tmp_path / "app/utils/__init__.py",
        ])
        judgments = check_framework_dependencies(
            graph, framework_packages=frozenset({"flask"}), dimension="clean-architecture",
        )

        assert [(j.practice_id, j.file) for j in judgments if j.verdict == "violation"] == [
            ("CLEA-DEP-06", "app/domain/order.py"),
        ]
