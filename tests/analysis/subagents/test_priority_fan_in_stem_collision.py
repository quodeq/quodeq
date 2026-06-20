"""Tests for stem-collision dedup in compute_fan_in (finding #522).

When two files share the same stem (e.g. a/util.py and b/util.py) the original
setdefault(stem, path) map kept only the FIRST; the second was silently dropped
from import-target resolution, giving it a permanent fan-in of zero.

Fix: the map value is now a list/set of all paths sharing a stem; the resolution
consumer checks all candidates and returns the one that matches.
"""
from __future__ import annotations

from pathlib import Path
import pytest

from quodeq.analysis.subagents.priority_fan_in import compute_fan_in


class TestStemCollisionDedup:
    """Both files with the same stem must be resolvable as import targets."""

    def test_both_stems_counted_when_different_dirs(self, tmp_path: Path) -> None:
        """a/util.py and b/util.py both get fan-in credit when imported."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        # importer_a imports from a/util
        (tmp_path / "importer_a.py").write_text("from a.util import something\n")
        # importer_b imports from b/util
        (tmp_path / "importer_b.py").write_text("from b.util import other\n")
        (tmp_path / "a" / "util.py").write_text("# util in a\n")
        (tmp_path / "b" / "util.py").write_text("# util in b\n")

        files = [
            "importer_a.py",
            "importer_b.py",
            "a/util.py",
            "b/util.py",
        ]
        fan_in = compute_fan_in(files, tmp_path, "python")

        # Both util files must appear with non-zero fan-in, not just the first one
        a_util = fan_in.get("a/util.py", 0)
        b_util = fan_in.get("b/util.py", 0)
        assert a_util >= 1, (
            f"a/util.py has fan-in {a_util}; stem-collision dropped it (got {fan_in})"
        )
        assert b_util >= 1, (
            f"b/util.py has fan-in {b_util}; stem-collision dropped it (got {fan_in})"
        )

    def test_second_registered_stem_not_silently_dropped(self, tmp_path: Path) -> None:
        """The file registered SECOND for a given stem must not be zero-count
        when it is the only file being imported under that stem."""
        (tmp_path / "x").mkdir()
        (tmp_path / "y").mkdir()
        # Only y/models is imported; x/models is never referenced.
        (tmp_path / "main.py").write_text("from y.models import Foo\n")
        (tmp_path / "x" / "models.py").write_text("")
        (tmp_path / "y" / "models.py").write_text("")

        files = [
            "main.py",
            "x/models.py",  # registered first — old bug would keep only this
            "y/models.py",  # registered second — old bug dropped this
        ]
        fan_in = compute_fan_in(files, tmp_path, "python")

        y_models = fan_in.get("y/models.py", 0)
        assert y_models >= 1, (
            f"y/models.py (registered second) has fan-in {y_models}; "
            f"stem-collision dedup is not working (got {fan_in})"
        )

    def test_unique_stems_unaffected(self, tmp_path: Path) -> None:
        """Files with unique stems continue to work correctly after the fix."""
        (tmp_path / "main.py").write_text("import auth\nfrom utils import helper\n")
        (tmp_path / "auth.py").write_text("")
        (tmp_path / "utils.py").write_text("")

        files = ["main.py", "auth.py", "utils.py"]
        fan_in = compute_fan_in(files, tmp_path, "python")

        assert fan_in.get("auth.py", 0) >= 1
        assert fan_in.get("utils.py", 0) >= 1

    def test_three_way_stem_collision(self, tmp_path: Path) -> None:
        """Three files with the same stem across three directories all get credit."""
        for d in ("p1", "p2", "p3"):
            (tmp_path / d).mkdir()
        (tmp_path / "use_p1.py").write_text("from p1.helpers import foo\n")
        (tmp_path / "use_p2.py").write_text("from p2.helpers import bar\n")
        (tmp_path / "use_p3.py").write_text("from p3.helpers import baz\n")
        for d in ("p1", "p2", "p3"):
            (tmp_path / d / "helpers.py").write_text("")

        files = [
            "use_p1.py", "use_p2.py", "use_p3.py",
            "p1/helpers.py", "p2/helpers.py", "p3/helpers.py",
        ]
        fan_in = compute_fan_in(files, tmp_path, "python")
        for path in ("p1/helpers.py", "p2/helpers.py", "p3/helpers.py"):
            assert fan_in.get(path, 0) >= 1, (
                f"{path} has fan-in {fan_in.get(path, 0)} — stem-collision fix incomplete"
            )
