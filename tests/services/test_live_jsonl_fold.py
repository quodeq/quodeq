"""The live findings JSONL is folded incrementally across polls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from quodeq.services import live_jsonl_fold
from quodeq.services.live_jsonl_fold import AppendedLines, fold_for


@pytest.fixture(autouse=True)
def _fresh_folds():
    live_jsonl_fold.clear()
    yield
    live_jsonl_fold.clear()


def _row(i: int) -> str:
    return json.dumps({"p": "P1", "t": "violation", "file": f"f{i}.py", "line": i}) + "\n"


def _counting_parser(seen_batches: list[list[str]]):
    def new_parser():
        def parse(lines):
            batch = list(lines)
            seen_batches.append(batch)
            return batch, []
        return parse
    return new_parser


def test_only_the_appended_lines_are_parsed(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.write_text(_row(1) + _row(2))
    batches: list[list[str]] = []
    fold = fold_for(path, ("id",), _counting_parser(batches))

    fold.advance()
    with path.open("a") as f:
        f.write(_row(3))
    fold.advance()
    fold.advance()

    assert [len(b) for b in batches] == [2, 1]
    assert len(fold.violations) == 3


def test_a_partial_trailing_line_waits_for_the_next_poll(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.write_text(_row(1) + '{"p": "P1"')
    lines = AppendedLines(path)

    assert lines.read() == (False, [_row(1).rstrip("\n")])
    with path.open("a") as f:
        f.write(', "t": "violation"}\n')
    assert lines.read() == (False, ['{"p": "P1", "t": "violation"}'])


def test_a_rewritten_file_starts_the_fold_over(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.write_text(_row(1) + _row(2) + _row(3))
    batches: list[list[str]] = []
    fold = fold_for(path, ("id",), _counting_parser(batches))
    fold.advance()

    path.write_text(_row(1))  # the end-of-pool dedup pass rewrites in place
    fold.advance()

    assert len(fold.violations) == 1


def test_a_new_identity_rebuilds_the_fold(tmp_path: Path) -> None:
    path = tmp_path / "f.jsonl"
    path.write_text(_row(1))
    first = fold_for(path, ("before-dismiss",), _counting_parser([]))

    assert fold_for(path, ("before-dismiss",), _counting_parser([])) is first
    assert fold_for(path, ("after-dismiss",), _counting_parser([])) is not first
