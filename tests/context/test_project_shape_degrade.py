"""detect_shape never raises: pathological manifests degrade, absent ones stay quiet."""
import logging
from pathlib import Path

import pytest

from quodeq.context.project_shape import Deployment, detect_shape

from ._project_shape_helpers import _write


class TestPathologicalManifestsDegrade:
    """detect_shape must never fail a scan over a manifest it cannot read.

    Its contract is "fall back to UNKNOWN whenever signals are absent or
    contradictory", and four callers (_api_runner, api_prompt_assembly,
    mcp/findings_server, and context/__init__'s re-export) invoke it with no
    guard of their own. Anything that escapes here fails the run.

    The manifests below are all *analyzed*, untrusted input from the repo
    under evaluation, not files Quodeq controls.
    """

    def test_deeply_nested_package_json(self, tmp_path: Path, deeply_nested_json: str) -> None:
        # _read_json caught only json.JSONDecodeError. Nesting deep enough to
        # exhaust the C decoder's call stack raises RecursionError instead --
        # a RuntimeError subclass, so it escaped.
        _write(tmp_path / "package.json", deeply_nested_json)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_pyproject_toml(self, tmp_path: Path) -> None:
        # Same class through tomllib, which is a pure-Python recursive-descent
        # parser and so overflows at a much shallower depth than the C JSON
        # decoder. _read_toml caught only OSError/TOMLDecodeError.
        _write(tmp_path / "pyproject.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_cargo_toml(self, tmp_path: Path) -> None:
        # _rust_signals shares _read_toml, so Cargo.toml is the same hole.
        _write(tmp_path / "Cargo.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_dependencies_that_are_not_a_list(self, tmp_path: Path) -> None:
        """Not a RecursionError, and not fixed by widening the readers.

        ``dependencies = 5`` parses as perfectly valid TOML, so every reader
        succeeds; _python_signals then did ``list(deps_list)`` on an int and
        raised TypeError. Guarding only the readers would leave this escape
        open, which is the whole point of fixing detect_shape at the source
        rather than wrapping each caller.
        """
        _write(tmp_path / "pyproject.toml", '[project]\nname = "x"\ndependencies = 5\n')
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_a_readable_manifest_still_detects_after_a_broken_sibling(
        self, tmp_path: Path, deeply_nested_json: str,
    ) -> None:
        """Degrading is per-manifest, not all-or-nothing.

        A pathological package.json must not blank the verdict a perfectly
        good pyproject.toml supports -- otherwise the fix trades a crash for
        silent, total detection loss.
        """
        _write(tmp_path / "package.json", deeply_nested_json)
        _write(
            tmp_path / "pyproject.toml",
            '[project]\nname = "x"\ndependencies = ["flask>=3.0"]\n',
        )
        shape = detect_shape(tmp_path)
        assert shape.deployment is Deployment.WEB_SERVICE
        assert shape.web_frameworks == ["flask"]


class TestAbsentManifestsAreNotWarnings:
    """A manifest a project simply does not ship is not a problem to report.

    detect_shape probes every manifest it knows about, so most repos miss most
    of them, and it runs per routing pass rather than once per scan. Logging
    absence at WARNING put two lines of "[Errno 2] No such file" into the scan
    output every few seconds for a Python project with no Cargo.toml.
    """

    def _records(self, caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
        return [
            r.getMessage() for r in caplog.records
            if r.name == "quodeq.context.project_shape" and r.levelno == level
        ]

    def test_missing_manifests_log_at_debug_not_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        with caplog.at_level(logging.DEBUG, logger="quodeq.context.project_shape"):
            assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN
        assert self._records(caplog, logging.WARNING) == []
        assert self._records(caplog, logging.DEBUG)

    def test_a_manifest_that_exists_but_cannot_be_parsed_still_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Quieting absence must not quiet a signal we meant to have and lost."""
        _write(tmp_path / "pyproject.toml", "[project\nname = ")
        with caplog.at_level(logging.DEBUG, logger="quodeq.context.project_shape"):
            assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN
        warnings = self._records(caplog, logging.WARNING)
        assert len(warnings) == 1
        assert "pyproject.toml" in warnings[0]

    def test_a_directory_named_like_a_manifest_is_absence_not_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A directory named like a manifest means no manifest, same as none.

        This is why the not-a-file cases are settled by ``is_file()`` rather
        than by exception type: opening a directory raises IsADirectoryError
        on POSIX but PermissionError (WinError 5) on Windows, which no handler
        can tell apart from a real permission denial. Classifying on the
        exception alone passed here and warned on Windows.

        The patches below make that platform difference reproducible off
        Windows: they force the POSIX-only exception to be the wrong one, so
        the test fails anywhere if the ``is_file()`` gate stops running before
        the open. Without them this test passes on macOS and Linux either way.
        """
        def _windows_style_denial(*_a: object, **_kw: object) -> None:
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(Path, "read_text", _windows_style_denial)
        monkeypatch.setattr(Path, "open", _windows_style_denial)
        (tmp_path / "package.json").mkdir()
        (tmp_path / "Cargo.toml").mkdir()
        with caplog.at_level(logging.DEBUG, logger="quodeq.context.project_shape"):
            assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN
        assert self._records(caplog, logging.WARNING) == []

    def test_a_manifest_that_vanishes_after_the_check_is_quiet(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The is_file() gate leaves a TOCTOU window the handler still covers.

        Forcing is_file() True over an empty directory is the only way to
        reach that window deterministically; without it the handler is
        unreachable on every platform and so untested. Language-marker
        detection reads exists(), not is_file(), so the verdict is unaffected.
        """
        monkeypatch.setattr(Path, "is_file", lambda self: True)
        with caplog.at_level(logging.DEBUG, logger="quodeq.context.project_shape"):
            assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN
        assert self._records(caplog, logging.WARNING) == []
        assert any("vanished" in m for m in self._records(caplog, logging.DEBUG))
