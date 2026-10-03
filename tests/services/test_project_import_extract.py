"""safe_extract never writes more bytes than the validated header declares."""
from __future__ import annotations

import io
import struct
import zipfile

import pytest

from quodeq.services.project_import import safe_extract

_CD_SIGNATURE = b"PK\x01\x02"
_CD_FILE_SIZE_OFFSET = 24  # uncompressed size field in a central directory entry


def _zip_with_lying_size(declared: int, payload: bytes) -> zipfile.ZipFile:
    """A zip whose central directory claims *declared* bytes for a larger member."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("u/big.txt", payload)
    raw = bytearray(buf.getvalue())
    struct.pack_into("<I", raw, raw.rfind(_CD_SIGNATURE) + _CD_FILE_SIZE_OFFSET, declared)
    return zipfile.ZipFile(io.BytesIO(bytes(raw)))


def test_lying_file_size_header_cannot_inflate_extraction(tmp_path):
    """The validators trust ZipInfo.file_size; the stdlib reader stops at that
    size and fails the CRC, so a small declared size cannot write a large file."""
    declared = 10
    zf = _zip_with_lying_size(declared, b"A" * (4 * 1024 * 1024))
    info = zf.infolist()[0]
    assert info.file_size == declared

    with pytest.raises(zipfile.BadZipFile):
        safe_extract(zf, {"u/big.txt": info}, tmp_path)

    assert (tmp_path / "u" / "big.txt").stat().st_size <= declared
