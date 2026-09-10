"""_tail_new_lines: a TOCTOU race between the caller's path.exists() check and
open() must end in an SSE error frame, not an uncaught FileNotFoundError
escaping the streaming generator (cluster 10, fault-tolerance cycle 1).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.api._sse_log_helpers import _tail_new_lines


def _drain(gen):
    """Collect all yielded frames plus the generator's return value."""
    frames = []
    try:
        while True:
            frames.append(next(gen))
    except StopIteration as si:
        return frames, si.value


class TestTailNewLinesRace:
    def test_missing_file_yields_error_frame_instead_of_raising(self, tmp_path: Path):
        missing = tmp_path / "gone.log"
        gen = _tail_new_lines(missing, 5, None)

        frames, new_offset = _drain(gen)

        assert len(frames) == 1
        assert "event: error" in frames[0]
        # Offset is left unchanged on failure so the caller's next poll tick
        # can retry from the same position.
        assert new_offset == 5

    def test_existing_file_still_tails_normally(self, tmp_path: Path):
        path = tmp_path / "run.log"
        path.write_text("hello\n", encoding="utf-8")
        gen = _tail_new_lines(path, 0, None)

        frames, new_offset = _drain(gen)

        assert len(frames) == 1
        assert "event: error" not in frames[0]
        assert "data: hello" in frames[0]
        assert new_offset == len("hello\n")
