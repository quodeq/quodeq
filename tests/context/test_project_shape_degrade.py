"""detect_shape never raises: pathological manifests degrade, absent ones stay quiet."""
import json
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
        # read_json caught only json.JSONDecodeError. Nesting deep enough to
        # exhaust the C decoder's call stack raises RecursionError instead --
        # a RuntimeError subclass, so it escaped.
        _write(tmp_path / "package.json", deeply_nested_json)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_pyproject_toml(self, tmp_path: Path) -> None:
        # Same class through tomllib, which is a pure-Python recursive-descent
        # parser and so overflows at a much shallower depth than the C JSON
        # decoder. read_toml caught only OSError/TOMLDecodeError.
        _write(tmp_path / "pyproject.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_deeply_nested_cargo_toml(self, tmp_path: Path) -> None:
        # rust_signals shares read_toml, so Cargo.toml is the same hole.
        _write(tmp_path / "Cargo.toml", "a = " + "[" * 5000 + "]" * 5000)
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_dependencies_that_are_not_a_list(self, tmp_path: Path) -> None:
        """Not a RecursionError, and not fixed by widening the readers.

        ``dependencies = 5`` parses as perfectly valid TOML, so every reader
        succeeds; python_signals then did ``list(deps_list)`` on an int and
        raised TypeError. Guarding only the readers would leave this escape
        open, which is the whole point of fixing detect_shape at the source
        rather than wrapping each caller.
        """
        _write(tmp_path / "pyproject.toml", '[project]\nname = "x"\ndependencies = 5\n')
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_non_utf8_package_json_degrades(self, tmp_path: Path) -> None:
        """read_text (called through read_json) narrows to
        (OSError, UnicodeDecodeError): invalid UTF-8 bytes must degrade the
        signal, not crash the scan."""
        (tmp_path / "package.json").write_bytes(b'{"name": "\xff\xfe bad utf8"}')
        assert detect_shape(tmp_path).deployment is Deployment.UNKNOWN

    def test_non_utf8_pyproject_toml_degrades(self, tmp_path: Path) -> None:
        """read_toml narrows to (OSError, ValueError, RecursionError):
        tomllib.load raises UnicodeDecodeError (a ValueError subclass) on
        non-UTF-8 bytes, which must degrade the signal, not crash the scan."""
        (tmp_path / "pyproject.toml").write_bytes(b'[project]\nname = "\xff\xfe"\n')
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


class TestUnnamedReaderErrorsPropagate:
    """Each _project_shape_io reader narrows to a specific tuple; anything
    outside it is a real bug, not a malformed-manifest signal, and must
    propagate rather than degrade. detect_shape's own except narrows to
    (OSError, TypeError) (project_shape.py), so an exception belonging to
    neither a reader's tuple nor that one reaches the caller untouched --
    proof the reader itself doesn't swallow it."""

    def test_read_text_unnamed_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """read_text narrows to (OSError, UnicodeDecodeError); reached here
        through go_signals' main.go read, the only read_text call site not
        also covered by read_json."""
        (tmp_path / "go.mod").write_text("module example.com/tool\n\ngo 1.21\n", encoding="utf-8")
        (tmp_path / "main.go").write_text("package main\n\nfunc main() {}\n", encoding="utf-8")

        def _boom(*_a: object, **_kw: object) -> None:
            raise LookupError("unexpected")

        monkeypatch.setattr(Path, "read_text", _boom)
        with pytest.raises(LookupError):
            detect_shape(tmp_path)

    def test_read_toml_unnamed_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """read_toml narrows to (OSError, ValueError, RecursionError),
        reached through python_signals' pyproject.toml read (the first
        manifest detect_shape probes)."""
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

        def _boom(*_a: object, **_kw: object) -> None:
            raise LookupError("unexpected")

        monkeypatch.setattr(Path, "open", _boom)
        with pytest.raises(LookupError):
            detect_shape(tmp_path)

    def test_read_json_unnamed_error_propagates(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """read_json narrows to (ValueError, RecursionError). The read
        itself must succeed (a real, valid package.json) so the failure is
        isolated to json.loads, not to read_text underneath it."""
        (tmp_path / "package.json").write_text('{"dependencies": {}}', encoding="utf-8")

        def _boom(*_a: object, **_kw: object) -> None:
            raise LookupError("unexpected")

        monkeypatch.setattr(json, "loads", _boom)
        with pytest.raises(LookupError):
            detect_shape(tmp_path)


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
