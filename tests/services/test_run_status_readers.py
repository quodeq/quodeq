from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from quodeq.services._run_status_readers import _read_enriched_status_fields


def _write_status(run_dir: Path, **fields) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(json.dumps(fields), encoding="utf-8")


def test_reads_status_json_once_for_all_four_fields(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_status(
        run_dir,
        dimensions=["security", "performance"],
        deadline_at="2026-09-02T20:00:00+00:00",
        ai_provider="claude",
        ai_model="sonnet",
        time_limit_s=3600,
    )

    real_read_text = Path.read_text
    read_count = {"n": 0}

    def counting_read_text(self, *a, **kw):
        if self.name == "status.json":
            read_count["n"] += 1
        return real_read_text(self, *a, **kw)

    with patch("pathlib.Path.read_text", counting_read_text):
        logs, dims, deadline, provider, model, limit = _read_enriched_status_fields(run_dir)

    assert dims == ["security", "performance"]
    assert deadline == "2026-09-02T20:00:00+00:00"
    assert provider == "claude"
    assert model == "sonnet"
    assert limit == 3600
    assert read_count["n"] == 1, f"expected 1 status.json read, got {read_count['n']}"


def test_missing_status_json_returns_all_nones(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    logs, dims, deadline, provider, model, limit = _read_enriched_status_fields(run_dir)
    assert (dims, deadline, provider, model, limit) == (None, None, None, None, None)


class _ReadSpy:
    """Delegates to a real file object while tallying every byte/char pulled
    from it, across both ``read()`` and ``readline()``.

    A plain ``fh.read = wrapper`` instance-attribute override (as one might
    first reach for) is silently ignored by ``TextIOWrapper.readlines()``:
    that method is implemented in C and calls the underlying buffer directly,
    bypassing Python-level attribute lookup on ``read``/``readline``, and the
    relevant CPython IO types are immutable (`_io.TextIOWrapper`, `_io.FileIO`)
    so their methods can't be monkeypatched at the class level either. Wrapping
    the returned handle in a plain Python object -- so ``readlines()`` (old
    code) and explicit ``seek``/``read`` calls (new code) both go through our
    overridden methods -- avoids that trap and lets ``total_read`` reflect
    what was actually pulled off disk either way.
    """

    def __init__(self, real):
        self._real = real
        self.total_read = 0

    def read(self, size=-1, *a, **kw):
        data = self._real.read(size, *a, **kw)
        self.total_read += len(data)
        return data

    def readline(self, *a, **kw):
        data = self._real.readline(*a, **kw)
        self.total_read += len(data)
        return data

    def readlines(self, *a, **kw):
        lines = []
        while True:
            line = self.readline()
            if not line:
                break
            lines.append(line)
        return lines

    def __iter__(self):
        return iter(self.readlines())

    def __getattr__(self, name):
        return getattr(self._real, name)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self._real.close()


def test_tail_run_log_does_not_read_whole_file(tmp_path: Path, monkeypatch):
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log_path = run_dir / "run.log"
    # 2000 short lines -- big enough that a whole-file read is easy to detect
    # via a read-size ceiling, small enough the test stays fast.
    log_path.write_text("\n".join(f"line-{i}" for i in range(2000)) + "\n", encoding="utf-8")

    real_open = Path.open
    spies: list[_ReadSpy] = []

    def counting_open(self, *a, **kw):
        fh = real_open(self, *a, **kw)
        if self != log_path:
            return fh
        spy = _ReadSpy(fh)
        spies.append(spy)
        return spy

    monkeypatch.setattr(Path, "open", counting_open)

    tail = _tail_run_log(run_dir, max_lines=500)

    assert len(tail) == 500
    assert tail == [f"line-{i}" for i in range(1500, 2000)]
    file_size = log_path.stat().st_size
    total_read = sum(spy.total_read for spy in spies)
    assert total_read < file_size, (
        f"expected a bounded read (<{file_size} bytes total), got {total_read} bytes read"
    )


def test_tail_run_log_empty_file(tmp_path: Path):
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.log").write_text("", encoding="utf-8")

    assert _tail_run_log(run_dir, max_lines=500) == []


def test_tail_run_log_fewer_lines_than_max(tmp_path: Path):
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log_path = run_dir / "run.log"
    log_path.write_text("\n".join(f"line-{i}" for i in range(10)) + "\n", encoding="utf-8")

    tail = _tail_run_log(run_dir, max_lines=500)
    assert tail == [f"line-{i}" for i in range(10)]


def test_tail_run_log_no_trailing_newline(tmp_path: Path):
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log_path = run_dir / "run.log"
    # Truncated mid-line: no trailing \n on the last line.
    log_path.write_text("\n".join(f"line-{i}" for i in range(5)), encoding="utf-8")

    tail = _tail_run_log(run_dir, max_lines=500)
    assert tail == [f"line-{i}" for i in range(5)]


def test_tail_run_log_missing_file(tmp_path: Path):
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    assert _tail_run_log(run_dir, max_lines=500) == []


def test_tail_run_log_line_longer_than_chunk_size(tmp_path: Path):
    """A single line bigger than the initial 8KB chunk must survive chunk growth intact."""
    from quodeq.services._run_status_readers import _tail_run_log

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    log_path = run_dir / "run.log"
    long_line = "x" * 20000  # > 8192, forces at least one chunk doubling
    lines = [f"line-{i}" for i in range(5)] + [long_line] + [f"line-{i}" for i in range(5, 10)]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tail = _tail_run_log(run_dir, max_lines=500)
    assert tail == lines
