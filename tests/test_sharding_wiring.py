"""The shared conftest applies QUODEQ_TEST_SHARD to collection."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from tests._sharding import select_shard

_REPO = Path(__file__).resolve().parents[1]
# One file from each of two shards, so "1/2" has something to keep and
# something to drop. The precondition test below pins that they differ.
_IN_SHARD_1 = "tests/test_cli_help.py"
_IN_SHARD_2 = "tests/test_sharding.py"


class _Item:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid


def _collect(shard: str | None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "QUODEQ_TEST_SHARD"}
    if shard is not None:
        env["QUODEQ_TEST_SHARD"] = shard
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         _IN_SHARD_1, _IN_SHARD_2],
        cwd=_REPO, env=env, capture_output=True, text=True, check=False,
    )
    return done.stdout + done.stderr


def _counts(output: str) -> tuple[int, int]:
    """Return ``(collected, deselected)`` from pytest's collect-only summary."""
    m = re.search(r"(\d+)(?:/\d+)? tests? collected(?: \((\d+) deselected\))?", output)
    assert m, output
    return int(m.group(1)), int(m.group(2) or 0)


def test_the_probe_files_sit_in_different_shards():
    kept, dropped = select_shard([_Item(_IN_SHARD_1), _Item(_IN_SHARD_2)], 1, 2)
    assert [i.nodeid for i in kept] == [_IN_SHARD_1]
    assert [i.nodeid for i in dropped] == [_IN_SHARD_2]


def test_a_shard_deselects_the_files_that_hash_elsewhere():
    whole, _ = _counts(_collect(None))
    output = _collect("1/2")
    collected, deselected = _counts(output)
    listed = [line for line in output.splitlines() if "::" in line]
    assert listed and all(line.startswith(_IN_SHARD_1) for line in listed), output
    assert deselected > 0
    assert collected + deselected == whole


def test_unset_leaves_collection_untouched():
    _, deselected = _counts(_collect(None))
    assert deselected == 0
