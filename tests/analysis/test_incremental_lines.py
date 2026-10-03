"""Multi-byte UTF-8 characters must decode cleanly even when a chunk
boundary lands mid-character, and every byte read must still be counted."""
from __future__ import annotations

from pathlib import Path

from quodeq.analysis.stream.progress_reader import iter_line_batches


def test_multibyte_char_split_across_chunks_decodes_cleanly(tmp_path: Path):
    p = tmp_path / "s.jsonl"
    p.write_bytes(b"ab" + "é".encode() + b"\n")
    batches = list(iter_line_batches(p, 0, chunk=3))
    lines = [line for batch, _ in batches for line in batch]
    assert lines == ["abé"]
    assert sum(n for _, n in batches) == p.stat().st_size


def test_file_ending_mid_character_still_counts_every_byte(tmp_path: Path):
    p = tmp_path / "s.jsonl"
    p.write_bytes(b"x\n" + b"y\xc3")
    batches = list(iter_line_batches(p, 0, chunk=2))
    assert sum(n for _, n in batches) == p.stat().st_size
