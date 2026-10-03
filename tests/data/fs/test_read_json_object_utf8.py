"""read_json_object and the project_files readers on non-UTF-8, missing and non-object files."""
from __future__ import annotations

import pytest

from quodeq.data.fs.project_files import (
    REPOSITORY_INFO_FILENAME,
    SCAN_FILENAME,
    read_repository_info,
    read_scan_json,
    read_scan_total_files,
)
from quodeq.data.fs.run_artifacts import read_json_object

_NOT_UTF8 = b'{"total_files": 3, "name": "\xff"}'


def test_generic_reader_reads_non_utf8_as_none(tmp_path):
    path = tmp_path / "x.json"
    path.write_bytes(_NOT_UTF8)
    assert read_json_object(path) is None


def test_project_record_readers_read_a_non_utf8_file_as_none(tmp_path):
    (tmp_path / REPOSITORY_INFO_FILENAME).write_bytes(_NOT_UTF8)
    (tmp_path / SCAN_FILENAME).write_bytes(_NOT_UTF8)
    assert read_repository_info(tmp_path) is None
    assert read_scan_json(tmp_path) is None


def test_scan_total_files_reads_a_non_utf8_scan_as_zero(tmp_path):
    (tmp_path / SCAN_FILENAME).write_bytes(_NOT_UTF8)
    assert read_scan_total_files(tmp_path) == 0


@pytest.mark.parametrize(("content", "total"), [
    (None, 0), ("{", 0), ("[1]", 0), ('{"total_files": "7"}', 0), ('{"total_files": 7}', 7),
])
def test_scan_total_files(tmp_path, content, total):
    if content is not None:
        (tmp_path / SCAN_FILENAME).write_text(content, encoding="utf-8")
    assert read_scan_total_files(tmp_path) == total


@pytest.mark.parametrize("reader", [read_repository_info, read_scan_json])
@pytest.mark.parametrize("content", [None, "{", "[1]"])
def test_project_record_readers_return_none(tmp_path, reader, content):
    if content is not None:
        (tmp_path / REPOSITORY_INFO_FILENAME).write_text(content, encoding="utf-8")
        (tmp_path / SCAN_FILENAME).write_text(content, encoding="utf-8")
    assert reader(tmp_path) is None
