"""``iter_source_files`` drops binary files that share a source extension.

``.ts`` is both TypeScript and MPEG transport stream. Shaka Player keeps
video segments under test/assets/*.ts; the extension-only walk queued them
as TypeScript, the model could not parse a reply for any of them, and five
in a row tripped the failure-streak breaker, cancelling the whole run.
"""
from __future__ import annotations

from quodeq.analysis.manifest_models import ManifestWalkSpec
from quodeq.analysis.manifest_targets import WalkCounts, iter_source_files

# An MPEG-TS packet: sync byte 0x47, then a header with NUL bytes.
_MPEG_TS_PACKET = b"\x47\x40\x00\x10\x00\x00\xb0\x0d" + b"\xff" * 180


def _walk(tmp_path) -> list[str]:
    walk = ManifestWalkSpec(ext_map={".ts": "typescript"}, skip_dirs=set(), skip_patterns=[])
    return [rel for rel, _, _ in iter_source_files(tmp_path, tmp_path, walk, WalkCounts())]


def test_binary_file_with_source_extension_is_skipped(tmp_path) -> None:
    (tmp_path / "segment_0.ts").write_bytes(_MPEG_TS_PACKET * 4)
    (tmp_path / "player.ts").write_text("export const x: number = 1;\n", encoding="utf-8")

    assert _walk(tmp_path) == ["player.ts"]


def test_non_ascii_text_source_is_kept(tmp_path) -> None:
    (tmp_path / "i18n.ts").write_text("export const hi = 'héllo 世界';\n", encoding="utf-8")

    assert _walk(tmp_path) == ["i18n.ts"]


def test_empty_source_file_is_kept(tmp_path) -> None:
    (tmp_path / "index.ts").write_bytes(b"")

    assert _walk(tmp_path) == ["index.ts"]
