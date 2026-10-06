"""The state folder's instance id: created once, stable, and bound to the folder."""
from __future__ import annotations

import os
import stat
import sys

import pytest

from quodeq.shared.instance_id import INSTANCE_ID_FILE, read_instance_id


def test_first_read_creates_the_file_and_later_reads_return_the_same_id(tmp_path):
    env = {"QUODEQ_DIR": str(tmp_path)}
    first = read_instance_id(env)
    assert (tmp_path / INSTANCE_ID_FILE).read_text(encoding="utf-8").strip() == first
    assert len(first) == 32
    assert read_instance_id(env) == first


def test_a_replaced_state_folder_gets_a_different_id(tmp_path):
    before = read_instance_id({"QUODEQ_DIR": str(tmp_path / "a")})
    after = read_instance_id({"QUODEQ_DIR": str(tmp_path / "b")})
    assert before != after


def test_an_existing_id_is_read_as_is(tmp_path):
    (tmp_path / INSTANCE_ID_FILE).write_text("  kept-id \n", encoding="utf-8")
    assert read_instance_id({"QUODEQ_DIR": str(tmp_path)}) == "kept-id"


def test_an_empty_file_is_replaced_with_a_fresh_id(tmp_path):
    (tmp_path / INSTANCE_ID_FILE).write_text("", encoding="utf-8")
    fresh = read_instance_id({"QUODEQ_DIR": str(tmp_path)})
    assert len(fresh) == 32
    assert (tmp_path / INSTANCE_ID_FILE).read_text(encoding="utf-8").strip() == fresh


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs a folder the process cannot write")
def test_an_unwritable_folder_still_yields_an_id(tmp_path):
    folder = tmp_path / "ro"
    folder.mkdir()
    folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        got = read_instance_id({"QUODEQ_DIR": str(folder)})
    finally:
        folder.chmod(stat.S_IRWXU)
    assert len(got) == 32
    assert not (folder / INSTANCE_ID_FILE).exists()


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="needs a folder the process cannot write")
def test_an_unwritable_folder_yields_the_same_id_for_the_process(tmp_path):
    """/api/health is polled; an id minted per read would never match the UI's stored one."""
    first, second = tmp_path / "ro1", tmp_path / "ro2"
    for folder in (first, second):
        folder.mkdir()
        folder.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        a = read_instance_id({"QUODEQ_DIR": str(first)})
        again = read_instance_id({"QUODEQ_DIR": str(first)})
        other = read_instance_id({"QUODEQ_DIR": str(second)})
    finally:
        for folder in (first, second):
            folder.chmod(stat.S_IRWXU)
    assert a == again
    assert other != a
