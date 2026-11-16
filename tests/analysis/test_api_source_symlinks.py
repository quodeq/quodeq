"""API-mode source gathering never reads through a symlinked file.

API providers inline file contents into the prompt, so whatever the walk
yields leaves the machine with a cloud provider. ``os.walk`` does not descend
symlinked directories, but it does list symlinked files, and reading one
follows the link. A repository that commits ``leak.py -> ~/.ssh/id_rsa``
would otherwise send the key to the model. Every gathering path (manifest
walk, dispatch-time split, fallback gatherer) skips symlinks.
"""
from __future__ import annotations

import pytest

from quodeq.analysis.dispatch_policy import DispatchPolicy
from quodeq.analysis.manifest_models import ManifestWalkSpec
from quodeq.analysis.manifest_targets import WalkCounts, iter_source_files
from quodeq.analysis.subprocess import gather_source_files

_SECRET = "-----BEGIN OPENSSH PRIVATE KEY-----\n"


@pytest.fixture
def repo_with_escaping_link(tmp_path):
    """A repo holding one real source file and one link to a file outside it."""
    outside = tmp_path / "home" / ".ssh"
    outside.mkdir(parents=True)
    (outside / "id_rsa").write_text(_SECRET, encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
    try:
        (repo / "leak.py").symlink_to(outside / "id_rsa")
    except OSError:
        pytest.skip("symlinks unavailable on this platform")
    return repo


def test_manifest_walk_skips_symlinked_file(repo_with_escaping_link) -> None:
    repo = repo_with_escaping_link
    walk = ManifestWalkSpec(ext_map={".py": "python"}, skip_dirs=set(), skip_patterns=[])

    rels = [rel for rel, _, _ in iter_source_files(repo, repo, walk, WalkCounts())]

    assert rels == ["main.py"]


def test_manifest_walk_skips_link_even_when_git_tracks_it(repo_with_escaping_link) -> None:
    # A committed symlink is a tracked entry, so the tracked-files filter
    # alone lets it through.
    repo = repo_with_escaping_link
    tracked = {repo.resolve() / "main.py", repo.resolve() / "leak.py"}
    walk = ManifestWalkSpec(ext_map={".py": "python"}, skip_dirs=set(), skip_patterns=[],
                            tracked_files=tracked)

    rels = [rel for rel, _, _ in iter_source_files(repo, repo, walk, WalkCounts())]

    assert rels == ["main.py"]


def test_dispatch_split_excludes_symlinked_file(repo_with_escaping_link) -> None:
    # The queue may predate the link (or have been edited), so the
    # dispatch-time split re-checks before anything is read.
    policy = DispatchPolicy(provider_configs={}, ai_cmd="ollama", file_size_cap=1 << 20)

    dispatchable, excluded = policy.split_api_dispatchable(
        repo_with_escaping_link, ["main.py", "leak.py"])

    assert dispatchable == ["main.py"]
    assert excluded == ["leak.py"]


def test_dispatch_split_excludes_path_escaping_root(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside.py").write_text("x = 1\n", encoding="utf-8")
    policy = DispatchPolicy(provider_configs={}, ai_cmd="ollama", file_size_cap=1 << 20)

    dispatchable, excluded = policy.split_api_dispatchable(repo, ["../outside.py"])

    assert dispatchable == []
    assert excluded == ["../outside.py"]


def test_fallback_gatherer_skips_symlinked_file(repo_with_escaping_link) -> None:
    names = [f.name for f in gather_source_files(repo_with_escaping_link)]

    assert names == ["main.py"]


def test_fallback_gatherer_honours_quodeqignore(tmp_path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "keys.py").write_text("KEY = 'x'\n", encoding="utf-8")
    (tmp_path / ".quodeqignore").write_text("secrets/\n", encoding="utf-8")

    names = [f.name for f in gather_source_files(tmp_path)]

    assert names == ["main.py"]
