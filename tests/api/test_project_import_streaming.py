"""Project import sizes a seekable upload in place and spools the rest in chunks (6462)."""
from __future__ import annotations

import io
from pathlib import Path

from quodeq.api.import_project import import_zip_stream
from tests.api._project_import_fixtures import _make_zip, _patch_home

_MIB = 1024 * 1024


class _NonSeekableStream:
    """Upload stream that records every read size and cannot seek."""

    def __init__(self, data: bytes) -> None:
        self._buf = io.BytesIO(data)
        self.sizes: list[int] = []

    def read(self, n: int = -1) -> bytes:
        self.sizes.append(n)
        return self._buf.read(n)

    def seekable(self) -> bool:
        return False


class _UnreadableSeekable(io.BytesIO):
    """Seekable upload whose read() fails, so sizing it must not read it."""

    def read(self, n=-1):
        raise AssertionError("an oversized seekable upload must be rejected before any read")


def _reports(tmp_path: Path) -> Path:
    reports = tmp_path / "evaluations"
    reports.mkdir()
    return reports


def test_a_non_seekable_upload_is_copied_in_bounded_chunks(tmp_path):
    stream = _NonSeekableStream(_make_zip())
    with _patch_home(tmp_path.resolve()):
        outcome = import_zip_stream(stream, str(_reports(tmp_path)), None)
    assert outcome.status == 200, outcome.body
    assert stream.sizes and all(0 < n <= _MIB for n in stream.sizes)


def test_an_oversized_non_seekable_upload_stops_early(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_ZIP_SIZE_MB", "1")
    stream = _NonSeekableStream(b"x" * (3 * _MIB))
    outcome = import_zip_stream(stream, str(_reports(tmp_path)), None)
    assert outcome.body["code"] == "TOO_LARGE"
    assert sum(stream.sizes) <= 2 * _MIB


def test_a_seekable_oversized_upload_is_rejected_without_reading_it(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_MAX_ZIP_SIZE_MB", "1")
    upload = _UnreadableSeekable(b"x" * (3 * _MIB))
    outcome = import_zip_stream(upload, str(_reports(tmp_path)), None)
    assert outcome.body["code"] == "TOO_LARGE"


def test_a_seekable_upload_imports_in_place(tmp_path):
    with _patch_home(tmp_path.resolve()):
        outcome = import_zip_stream(io.BytesIO(_make_zip()), str(_reports(tmp_path)), None)
    assert outcome.status == 200, outcome.body
