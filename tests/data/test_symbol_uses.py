"""Finding a watched symbol however it was spelled.

``os.environ`` reaches a module under several names -- an aliased import, a
direct ``from os import environ``, a renamed one -- and a text search finds the
spelling you thought of. Binding each reference back to its canonical dotted
name is the whole job, and it needs the import statements, so it needs a parse.

The rule that keeps this precise: a reference only counts when the file
actually imported the thing. A local variable called ``os`` is not the standard
library.
"""
from __future__ import annotations

from quodeq.data.fs.symbol_uses import build_symbol_uses

WATCHED = frozenset({"os.environ", "os.getenv"})


def _write(root, rel: str, body: str):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _uses(tmp_path, body: str, names=WATCHED):
    _write(tmp_path, "app/x.py", body)
    found = build_symbol_uses(tmp_path, [tmp_path / "app/x.py"], names)
    return [(u.symbol, u.line) for u in found]


class TestSpellings:
    def test_plain_attribute_access(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = os.environ['X']\n") == [("os.environ", 2)]

    def test_aliased_module(self, tmp_path):
        assert _uses(tmp_path, "import os as o\nv = o.getenv('X')\n") == [("os.getenv", 2)]

    def test_from_import(self, tmp_path):
        assert _uses(tmp_path, "from os import environ\nv = environ['X']\n") == [
            ("os.environ", 2)]

    def test_from_import_renamed(self, tmp_path):
        assert _uses(tmp_path, "from os import getenv as ge\nv = ge('X')\n") == [
            ("os.getenv", 2)]

    def test_a_longer_chain_reports_the_watched_prefix(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = os.environ.get('X')\n") == [
            ("os.environ", 2)]

    def test_submodule_import_binds_the_top_package(self, tmp_path):
        assert _uses(tmp_path, "import os.path\nv = os.environ['X']\n") == [
            ("os.environ", 2)]


class TestPrecision:
    def test_a_local_name_that_was_never_imported_does_not_count(self, tmp_path):
        assert _uses(tmp_path, "os = {'a': 1}\nv = os.environ\n") == []

    def test_an_unwatched_symbol_is_ignored(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = os.getcwd()\n") == []

    def test_an_attribute_on_an_unrelated_object_is_ignored(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = cfg.environ\n") == []

    def test_repeated_use_on_one_line_is_recorded_once(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = os.environ['A'] + os.environ['B']\n") == [
            ("os.environ", 2)]

    def test_each_line_is_its_own_use(self, tmp_path):
        assert _uses(
            tmp_path, "import os\na = os.environ['A']\nb = os.environ['B']\n",
        ) == [("os.environ", 2), ("os.environ", 3)]


class TestFailSoft:
    def test_a_file_that_will_not_parse_contributes_nothing(self, tmp_path):
        _write(tmp_path, "app/broken.py", "def (:\n")

        assert build_symbol_uses(tmp_path, [tmp_path / "app/broken.py"], WATCHED) == ()

    def test_no_names_to_watch(self, tmp_path):
        assert _uses(tmp_path, "import os\nv = os.environ\n", frozenset()) == []

    def test_paths_outside_the_root_are_skipped(self, tmp_path):
        outside = tmp_path.parent / "outside_symbols.py"
        outside.write_text("import os\nv = os.environ\n", encoding="utf-8")
        root = tmp_path / "repo"
        root.mkdir()

        assert build_symbol_uses(root, [outside], WATCHED) == ()

    def test_results_are_sorted(self, tmp_path):
        _write(tmp_path, "app/b.py", "import os\nv = os.environ\n")
        _write(tmp_path, "app/a.py", "import os\nv = os.getenv('X')\n")

        found = build_symbol_uses(
            tmp_path, [tmp_path / "app/b.py", tmp_path / "app/a.py"], WATCHED,
        )

        assert [u.file for u in found] == ["app/a.py", "app/b.py"]


class TestEndToEndWithTheChecker:
    def test_an_env_read_in_a_domain_file_is_found_on_disk(self, tmp_path):
        from quodeq.core.checks.config_reads import CONFIG_SYMBOLS, check_config_reads
        from quodeq.data.fs.import_graph import build_import_graph

        _write(tmp_path, "app/__init__.py", "")
        _write(tmp_path, "app/domain/__init__.py", "")
        _write(tmp_path, "app/domain/pricing.py",
               "from os import getenv\n\n\ndef rate():\n    return getenv('RATE')\n")
        files = [tmp_path / "app/domain/pricing.py"]

        judgments = check_config_reads(
            build_import_graph(tmp_path, files),
            build_symbol_uses(tmp_path, files, CONFIG_SYMBOLS),
            dimension="clean-architecture",
        )

        assert [(j.practice_id, j.verdict, j.file, j.line) for j in judgments] == [
            ("CLEA-DEP-07", "violation", "app/domain/pricing.py", 5),
        ]
