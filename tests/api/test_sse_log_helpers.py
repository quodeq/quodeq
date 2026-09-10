"""_tail_new_lines: a TOCTOU race between the caller's path.exists() check and
open() must end in an SSE error frame, not an uncaught FileNotFoundError
escaping the streaming generator (cluster 10, fault-tolerance cycle 1).

A persistent open failure (permission denied, run directory removed
mid-stream) must not turn into an unbounded error-frame flood: the stream
has to emit the error frame once and end, exactly like the sibling
``_wait_for_log_file`` timeout path (final review, Important 1).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.api._sse_log_helpers import _tail_new_lines, sse_tail_generator


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

        frames, (new_offset, status) = _drain(gen)

        assert len(frames) == 1
        assert "event: error" in frames[0]
        # Offset is left unchanged on failure; the caller stops rather than
        # retrying with it, so the value itself is not load-bearing.
        assert new_offset == 5
        assert status == "error"

    def test_existing_file_still_tails_normally(self, tmp_path: Path):
        path = tmp_path / "run.log"
        path.write_text("hello\n", encoding="utf-8")
        gen = _tail_new_lines(path, 0, None)

        frames, (new_offset, status) = _drain(gen)

        assert len(frames) == 1
        assert "event: error" not in frames[0]
        assert "data: hello" in frames[0]
        assert new_offset == len("hello\n")
        assert status == "continue"


class TestSseTailGeneratorErrorTermination:
    """Drive the real generator, not just _tail_new_lines, per the final
    review: the bug was in the caller's loop, so the regression test has to
    exercise the caller."""

    def test_persistent_open_failure_emits_one_error_frame_then_stops(
        self, tmp_path: Path, monkeypatch
    ):
        # A directory in place of the log file makes every open() attempt
        # fail (IsADirectoryError, an OSError subclass) on every poll tick,
        # simulating a persistent failure such as permission denied or the
        # run directory being removed mid-stream.
        path = tmp_path / "run.log"
        path.mkdir()

        monkeypatch.setattr("quodeq.api._sse_log_helpers._POLL_MS", 0)

        frames = list(sse_tail_generator(path, initial_offset=0))

        error_frames = [f for f in frames if "event: error" in f]
        assert len(error_frames) == 1
        assert "log file unavailable" in error_frames[0]
        # No exception text leaked into the frame body (test_no_exception_echo
        # guard covers this at the module level; assert it here too since the
        # frame content is exactly what regresses if the fix is reverted).
        assert "IsADirectoryError" not in error_frames[0]
