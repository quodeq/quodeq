"""parse_progress: git's --progress stderr lines into percent and bytes."""
from __future__ import annotations

import pytest

from quodeq.core.types.sync_phase import SyncKind, SyncPhase
from quodeq.data.fs.git_progress import ProgressUpdate, parse_progress


@pytest.mark.parametrize("line,expected", [
    ("Receiving objects:  45% (1200/2650), 12.30 MiB | 2.10 MiB/s", ProgressUpdate(45, 12897484)),
    ("Receiving objects: 100% (2650/2650), 27.80 MiB | 2.10 MiB/s, done.", ProgressUpdate(100, 29150412)),
    ("Receiving objects:   0% (1/2650)", ProgressUpdate(0, None)),
    ("Receiving objects:   7% (186/2650), 1.02 KiB | 1.02 KiB/s", ProgressUpdate(7, 1044)),
    ("Receiving objects:  99% (2623/2650), 980 bytes | 980 bytes/s", ProgressUpdate(99, 980)),
    ("Counting objects: 100% (12/12), done.", ProgressUpdate(0, None)),
    ("Compressing objects:  50% (6/12)", ProgressUpdate(0, None)),
    ("Resolving deltas:  30% (300/1000)", ProgressUpdate(30, None, SyncPhase.RESOLVING)),
    ("Resolving deltas: 100% (1000/1000), done.", ProgressUpdate(100, None, SyncPhase.RESOLVING)),
    ("Updating files:  12% (1200/9876)", ProgressUpdate(12, None, SyncPhase.CHECKOUT)),
    ("Checking out files:  99% (9800/9876)", ProgressUpdate(99, None, SyncPhase.CHECKOUT)),
    ("remote: Enumerating objects: 2650, done.", None),
    ("Cloning into '/tmp/x'...", None),
    ("", None),
    ("Receiving objects: lots", None),
])
def test_parse_progress(line, expected):
    assert parse_progress(line) == expected


def test_cr_and_crlf_are_stripped():
    assert parse_progress("Receiving objects:  45% (1200/2650), 12.30 MiB\r") == ProgressUpdate(45, 12897484)
    assert parse_progress("Receiving objects:  45% (1200/2650), 12.30 MiB\r\n") == ProgressUpdate(45, 12897484)


def test_receiving_updates_are_the_download_phase():
    assert parse_progress("Receiving objects:  45% (1200/2650), 12.30 MiB").phase is SyncPhase.DOWNLOADING
    assert parse_progress("Counting objects: 100% (12/12), done.").phase is SyncPhase.DOWNLOADING


def test_enums_are_the_wire_values():
    assert [m.value for m in SyncPhase] == ["connecting", "downloading", "resolving", "checkout", "reading", "done", "error"]
    assert [m.value for m in SyncKind] == ["connect", "refresh", "pull", "clone"]
