"""``iter_source_files`` tallies directories ``os.walk`` could not list.

Without ``onerror=``, ``os.walk`` silently skips an unreadable directory and
moves on -- a partially-scanned repo looked identical to a fully-scanned one.
``WalkCounts.unreadable_dirs`` makes that visible to the caller the same way
``skipped_untracked`` already does.
"""
from __future__ import annotations

import os

from quodeq.analysis import manifest_targets
from quodeq.analysis.manifest_models import ManifestWalkSpec
from quodeq.analysis.manifest_targets import WalkCounts, iter_source_files


def test_iter_source_files_counts_unreadable_dirs(tmp_path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    real_walk = os.walk

    def fake_walk(root, onerror=None, **kwargs):
        if onerror is not None:
            onerror(OSError(13, "Permission denied", str(tmp_path / "locked")))
        yield from real_walk(root, **kwargs)

    monkeypatch.setattr(manifest_targets.os, "walk", fake_walk)
    walk = ManifestWalkSpec(ext_map={".py": "python"}, skip_dirs=set(), skip_patterns=[])
    counts = WalkCounts()

    files = list(iter_source_files(tmp_path, tmp_path, walk, counts))

    # The walk itself is unaffected: it still yields whatever the real
    # os.walk could see.
    assert ("a.py", ".py", "python") in files
    assert counts.unreadable_dirs == 1


def test_iter_source_files_leaves_unreadable_dirs_at_zero_on_a_clean_walk(
    tmp_path,
) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    walk = ManifestWalkSpec(ext_map={".py": "python"}, skip_dirs=set(), skip_patterns=[])
    counts = WalkCounts()

    list(iter_source_files(tmp_path, tmp_path, walk, counts))

    assert counts.unreadable_dirs == 0
