"""Tests for shared/validation.py's path-safety helpers.

``jailed_run_dir`` is the RETURNING resolver used at every evidence run_dir
build site: CodeQL's default py/path-injection model does not recognize the
void ``validate_path_segment`` helper as a sanitizer, but it does recognize
an inline ``resolve()`` + ``is_relative_to()`` guard whose result dominates
the sink (the same shape as ``api._project_dir``). ``jailed_run_dir`` wraps
that guard in a function that returns the confined path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from quodeq.shared.validation import jailed_run_dir


class TestJailedRunDir:
    def test_returns_path_within_reports_root(self, tmp_path):
        run_dir = jailed_run_dir(tmp_path, "my-project", "20260301T120000")
        assert run_dir == (tmp_path / "my-project" / "20260301T120000").resolve()
        assert run_dir.is_relative_to(tmp_path.resolve())

    def test_accepts_uuid_run_id(self, tmp_path):
        run_id = "5f2b6c2e-2c1a-4b8e-9b1a-3f7a2e9d1234"
        run_dir = jailed_run_dir(tmp_path, "proj", run_id)
        assert run_dir == (tmp_path / "proj" / run_id).resolve()

    def test_rejects_traversal_run_id(self, tmp_path):
        with pytest.raises(ValueError):
            jailed_run_dir(tmp_path, "proj", "../..")

    def test_rejects_traversal_project(self, tmp_path):
        with pytest.raises(ValueError):
            jailed_run_dir(tmp_path, "../x", "run1")

    def test_rejects_absolute_run_id_segment(self, tmp_path):
        with pytest.raises(ValueError):
            jailed_run_dir(tmp_path, "proj", "/etc/passwd")

    def test_rejects_separator_in_project(self, tmp_path):
        with pytest.raises(ValueError):
            jailed_run_dir(tmp_path, "proj/evil", "run1")

    def test_rejects_backslash_segment(self, tmp_path):
        with pytest.raises(ValueError):
            jailed_run_dir(tmp_path, "proj", "..\\..\\etc")

    def test_nonexistent_reports_root_still_resolves(self):
        """reports_root need not exist on disk for the guard to work: Path.resolve()
        with strict=False (the default) just normalizes, it doesn't require the
        path to exist."""
        run_dir = jailed_run_dir(Path("/reports"), "proj", "run1")
        assert run_dir == Path("/reports/proj/run1")
