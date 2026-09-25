"""_tail_new_lines: a TOCTOU race between the caller's path.exists() check and
open() must end in an SSE error frame, not an uncaught FileNotFoundError
escaping the streaming generator.

A persistent open failure (permission denied, run directory removed
mid-stream) must not turn into an unbounded error-frame flood: the stream
has to emit the error frame once and end, exactly like the sibling
``_wait_for_log_file`` timeout path (final review, Important 1).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.api._sse_log_helpers import (
    DEFAULT_TAIL_MAX_BYTES,
    ENV_TAIL_MAX_BYTES,
    _tail_new_lines,
    sse_tail_generator,
    tail_max_bytes,
)


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

        monkeypatch.setattr("quodeq.api._sse_log_helpers._poll_ms", lambda env=None: 0)

        frames = list(sse_tail_generator(path, initial_offset=0))

        error_frames = [f for f in frames if "event: error" in f]
        assert len(error_frames) == 1
        assert "log file unavailable" in error_frames[0]
        # No exception text leaked into the frame body (test_no_exception_echo
        # guard covers this at the module level; assert it here too since the
        # frame content is exactly what regresses if the fix is reverted).
        assert "IsADirectoryError" not in error_frames[0]


class TestTailMaxBytes:
    """Per-tick byte cap: env override, fallbacks, and env injection."""

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(ENV_TAIL_MAX_BYTES, raising=False)
        assert tail_max_bytes() == DEFAULT_TAIL_MAX_BYTES

    def test_env_override_is_honoured(self, monkeypatch):
        monkeypatch.setenv(ENV_TAIL_MAX_BYTES, "2048")
        assert tail_max_bytes() == 2048

    def test_non_numeric_and_non_positive_fall_back(self, monkeypatch):
        monkeypatch.setenv(ENV_TAIL_MAX_BYTES, "not-a-number")
        assert tail_max_bytes() == DEFAULT_TAIL_MAX_BYTES
        monkeypatch.setenv(ENV_TAIL_MAX_BYTES, "0")
        assert tail_max_bytes() == DEFAULT_TAIL_MAX_BYTES

    def test_injected_empty_env_ignores_host_environment(self, monkeypatch):
        monkeypatch.setenv(ENV_TAIL_MAX_BYTES, "2048")
        assert tail_max_bytes(env={}) == DEFAULT_TAIL_MAX_BYTES

    def test_injected_env_is_read_instead_of_host(self, monkeypatch):
        monkeypatch.delenv(ENV_TAIL_MAX_BYTES, raising=False)
        assert tail_max_bytes(env={ENV_TAIL_MAX_BYTES: "4096"}) == 4096
