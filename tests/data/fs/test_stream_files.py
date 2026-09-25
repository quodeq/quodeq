"""append_jsonl_strict (raises on failure) and iter_stream_lines (read helper)."""
from __future__ import annotations

import os
import stat

import pytest

from quodeq.data.fs.stream_files import append_jsonl_strict, iter_stream_lines


class TestAppendJsonlStrict:
    def test_appends_one_line_per_row(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text('{"existing": 1}\n')
        append_jsonl_strict(path, [{"a": 1}, {"b": 2}])
        lines = path.read_text().splitlines()
        assert lines == ['{"existing": 1}', '{"a": 1}', '{"b": 2}']

    def test_append_false_truncates(self, tmp_path):
        path = tmp_path / "d_evidence.jsonl"
        path.write_text('{"stale": true}\n')
        append_jsonl_strict(path, [{"fresh": 1}], append=False)
        lines = path.read_text().splitlines()
        assert lines == ['{"fresh": 1}']

    @pytest.mark.skipif(
        os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
        reason="chmod-based permission denial is ineffective as root or on Windows",
    )
    def test_raises_oserror_on_unwritable_dir(self, tmp_path):
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        path = readonly_dir / "evidence.jsonl"
        readonly_dir.chmod(stat.S_IREAD | stat.S_IEXEC)
        try:
            with pytest.raises(OSError):
                append_jsonl_strict(path, [{"a": 1}])
        finally:
            readonly_dir.chmod(stat.S_IRWXU)


class TestIterStreamLines:
    def test_missing_file_yields_nothing(self, tmp_path):
        assert list(iter_stream_lines(tmp_path / "missing.stream")) == []

    def test_missing_file_yields_nothing_with_missing_ok_true_explicit(self, tmp_path):
        assert list(iter_stream_lines(tmp_path / "missing.stream", missing_ok=True)) == []

    def test_yields_stripped_nonempty_lines(self, tmp_path):
        path = tmp_path / "stream.jsonl"
        path.write_text('  {"a": 1}  \n\n{"b": 2}\n')
        assert list(iter_stream_lines(path)) == ['{"a": 1}', '{"b": 2}']

    def test_missing_ok_false_raises_filenotfounderror_on_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            list(iter_stream_lines(tmp_path / "missing.stream", missing_ok=False))

    def test_missing_ok_false_still_yields_lines_for_an_existing_file(self, tmp_path):
        path = tmp_path / "stream.jsonl"
        path.write_text('{"a": 1}\n')
        assert list(iter_stream_lines(path, missing_ok=False)) == ['{"a": 1}']
