"""The manifest walk scores what git tracks, not what is lying around (#1202).

An untracked scratch file no branch can reach must not reach a score, and the
same commit has to produce the same manifest in anyone's checkout. Outside a
git work tree, or when git cannot answer, nothing is filtered.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

from quodeq.analysis.manifest import build_manifest

from tests.analysis._manifest_fixtures import detection  # noqa: F401 -- pytest fixture

_LOGGER_NAME = "quodeq.analysis.manifest_build"
_SKIP_NEEDLE = "untracked file"


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def _write(path: Path, body: str = "x = 1\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _init_repo(path: Path) -> None:
    _run(["git", "init", "-q", "-b", "main"], path)
    _run(["git", "config", "user.email", "t@t"], path)
    _run(["git", "config", "user.name", "t"], path)


def _commit_all(path: Path) -> None:
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-q", "-m", "base"], path)


def _repo_with_committed(path: Path, names: list[str]) -> None:
    _init_repo(path)
    for name in names:
        _write(path / name)
    _commit_all(path)


def _raise_missing_git(*_args: object, **_kwargs: object) -> None:
    raise FileNotFoundError("git")


def _untracked_log_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if _SKIP_NEEDLE in r.getMessage()]


def test_untracked_file_is_not_scanned(tmp_path: Path, detection: dict) -> None:
    _repo_with_committed(tmp_path, ["app0.py", "app1.py", "app2.py"])
    _write(tmp_path / "scratch.py")

    manifest = build_manifest(tmp_path, detection)
    assert manifest.source_files == ["app0.py", "app1.py", "app2.py"]
    assert manifest.total_files == 3
    assert manifest.skipped_untracked == 1


def test_skipped_untracked_is_zero_without_git(tmp_path: Path, detection: dict) -> None:
    for name in ("app0.py", "app1.py", "app2.py"):
        _write(tmp_path / name)

    assert build_manifest(tmp_path, detection).skipped_untracked == 0


def test_staged_file_is_scanned(tmp_path: Path, detection: dict) -> None:
    """--cached sees the index, so `git add` is enough to be in scope.

    The untracked sibling is the control: without it this passes with the
    filter unwired entirely, which proves nothing about `--cached`.
    """
    _repo_with_committed(tmp_path, ["app0.py", "app1.py", "app2.py"])
    _write(tmp_path / "staged.py")
    _run(["git", "add", "staged.py"], tmp_path)
    _write(tmp_path / "scratch.py")

    manifest = build_manifest(tmp_path, detection)
    assert "staged.py" in manifest.source_files
    assert "scratch.py" not in manifest.source_files
    assert manifest.total_files == 4
    assert manifest.skipped_untracked == 1


def test_non_git_directory_scans_everything(tmp_path: Path, detection: dict) -> None:
    for name in ("app0.py", "app1.py", "app2.py", "scratch.py"):
        _write(tmp_path / name)

    manifest = build_manifest(tmp_path, detection)
    assert "scratch.py" in manifest.source_files
    assert manifest.total_files == 4


def test_git_failure_scans_everything(
    tmp_path: Path, detection: dict, monkeypatch,
) -> None:
    """No answer from git means no filtering, not an empty run."""
    _repo_with_committed(tmp_path, ["app0.py", "app1.py", "app2.py"])
    _write(tmp_path / "scratch.py")
    monkeypatch.setattr("quodeq.data.git_cli.subprocess.run", _raise_missing_git)

    manifest = build_manifest(tmp_path, detection)
    assert "scratch.py" in manifest.source_files
    assert manifest.total_files == 4


def test_scan_target_below_the_repo_root(tmp_path: Path, detection: dict) -> None:
    """src is a subdirectory of the repo, so the tracked listing has to be
    rebased onto the scan root rather than the repository root."""
    _repo_with_committed(
        tmp_path, ["top.py", "pkg/mod0.py", "pkg/mod1.py", "pkg/mod2.py"],
    )
    _write(tmp_path / "pkg" / "scratch.py")

    manifest = build_manifest(tmp_path / "pkg", detection)
    assert manifest.source_files == ["mod0.py", "mod1.py", "mod2.py"]


def test_pinned_scope_below_the_scan_root(tmp_path: Path, detection: dict) -> None:
    """The walk root is the pinned scope while paths stay relative to src."""
    _repo_with_committed(
        tmp_path, ["top.py", "pkg/mod0.py", "pkg/mod1.py", "pkg/mod2.py"],
    )
    _write(tmp_path / "pkg" / "scratch.py")

    manifest = build_manifest(tmp_path, detection, scope_path="pkg")
    assert manifest.source_files == ["pkg/mod0.py", "pkg/mod1.py", "pkg/mod2.py"]


def test_tracked_names_with_spaces_and_non_ascii(tmp_path: Path, detection: dict) -> None:
    """-z keeps odd names intact; git's default output would C-quote them."""
    names = ["plain.py", "two words.py", "héllo wörld.py"]
    _repo_with_committed(tmp_path, names)
    _write(tmp_path / "scratch.py")

    manifest = build_manifest(tmp_path, detection)
    assert sorted(manifest.source_files) == sorted(names)


def test_multi_scope_walk_filters_untracked(tmp_path: Path) -> None:
    """The monorepo walk shares _iter_source_files, so it filters too."""
    from quodeq.analysis.manifest_build_scope import _walk_and_partition_by_scope
    from quodeq.analysis.manifest_models import ManifestWalkSpec

    _write(tmp_path / "pkg" / "kept.py")
    _write(tmp_path / "pkg" / "scratch.py")
    spec = ManifestWalkSpec(
        ext_map={".py": "python"}, skip_dirs=set(), skip_patterns=[],
        tracked_files={(tmp_path / "pkg" / "kept.py").resolve()},
    )

    files_by_scope, _, _, skipped = _walk_and_partition_by_scope(tmp_path, spec, ["pkg"])
    assert files_by_scope["pkg"]["python"] == ["pkg/kept.py"]
    assert skipped == 1


def test_skipped_count_logged_once(tmp_path: Path, detection: dict, caplog) -> None:
    _repo_with_committed(tmp_path, ["app0.py", "app1.py", "app2.py"])
    _write(tmp_path / "scratch.py")
    _write(tmp_path / "notes.py")

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        manifest = build_manifest(tmp_path, detection)
    assert manifest.skipped_untracked == 2
    assert len(_untracked_log_lines(caplog)) == 1
    assert "Skipped 2 untracked files" in _untracked_log_lines(caplog)[0]


def test_nothing_logged_when_nothing_skipped(
    tmp_path: Path, detection: dict, caplog,
) -> None:
    _repo_with_committed(tmp_path, ["app0.py", "app1.py", "app2.py"])

    with caplog.at_level(logging.INFO, logger=_LOGGER_NAME):
        build_manifest(tmp_path, detection)
    assert _untracked_log_lines(caplog) == []


def _cli_prescan_stderr(tmp_path: Path, repo: Path, detection: dict, capsys) -> str:
    from quodeq._cli_resolution import build_cli_manifest

    detection_file = tmp_path / "detection.json"
    detection_file.write_text(json.dumps(detection), encoding="utf-8")
    paths = SimpleNamespace(
        detection_file=detection_file, disciplines_conf=tmp_path / "absent.conf",
    )
    build_cli_manifest(SimpleNamespace(no_prescan=False), repo, paths)
    return capsys.readouterr().err


def test_cli_prescan_reports_the_skipped_count(
    tmp_path: Path, detection: dict, capsys,
) -> None:
    """The count is on the manifest, so the prescan line can say it out loud
    even when nobody is reading the log."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_committed(repo, ["app0.py", "app1.py", "app2.py"])
    _write(repo / "scratch.py")

    err = _cli_prescan_stderr(tmp_path, repo, detection, capsys)
    assert "Source files: 3" in err
    assert "Skipped 1 untracked file (" in err


def test_cli_prescan_silent_when_nothing_skipped(
    tmp_path: Path, detection: dict, capsys,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo_with_committed(repo, ["app0.py", "app1.py", "app2.py"])

    assert _SKIP_NEEDLE not in _cli_prescan_stderr(tmp_path, repo, detection, capsys)
