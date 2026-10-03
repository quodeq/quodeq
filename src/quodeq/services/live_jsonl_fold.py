"""The live findings JSONL, folded incrementally across polls.

The Evaluate screen polls every 2 s while agents append to the dimension's
findings JSONL. Re-parsing the whole file on each poll made a run O(n^2) in
its findings. A fold remembers how far it read and only consumes the bytes
appended since, the same way ``IncrementalTally`` does for the progress
counts. A shrink or a rewritten tail (the end-of-pool dedup pass) or a
suppression change starts the fold over.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from pathlib import Path

from quodeq.core.types import Finding
from quodeq.shared.appended_lines import AppendedLines
from quodeq.shared.lru import LRUDict

_FOLDS_MAX = 16  # two 7-dimension runs' worth; the screen polls one run at a time


class FindingsFold:
    """Violation and compliance rows of one findings file, kept up to date."""

    def __init__(
        self, path: Path, identity: tuple,
        new_parser: Callable[[], Callable[[Iterable[str]], tuple[list[Finding], list[Finding]]]],
    ) -> None:
        self.identity = identity
        self.lock = threading.Lock()
        self._lines = AppendedLines(path)
        self._new_parser = new_parser
        self._reset()

    def _reset(self) -> None:
        self._parse = self._new_parser()
        self.violations: list[Finding] = []
        self.compliance: list[Finding] = []

    def advance(self) -> None:
        """Fold in the lines appended since the last call. Caller holds ``lock``."""
        restarted, lines = self._lines.read()
        if restarted:
            self._reset()
        if lines:
            violations, compliance = self._parse(lines)
            self.violations.extend(violations)
            self.compliance.extend(compliance)


class StreamFiles:
    """The set of files an agent stream has read, kept up to date."""

    def __init__(self, path: Path, extract: Callable[[str], Iterable[str]]) -> None:
        self._lines = AppendedLines(path)
        self._extract = extract
        self.files: set[str] = set()

    def advance(self) -> int:
        """Fold in the lines appended since the last call; return the file count."""
        restarted, lines = self._lines.read()
        if restarted:
            self.files = set()
        for line in lines:
            self.files.update(self._extract(line))
        return len(self.files)


_FOLDS: LRUDict[str, FindingsFold] = LRUDict(_FOLDS_MAX)
_STREAMS: LRUDict[str, StreamFiles] = LRUDict(_FOLDS_MAX)
_REGISTRY_LOCK = threading.Lock()


def fold_for(
    path: Path, identity: tuple,
    new_parser: Callable[[], Callable[[Iterable[str]], tuple[list[Finding], list[Finding]]]],
) -> FindingsFold:
    """The fold for *path*, rebuilt when *identity* (suppressions, standards) changed."""
    key = str(path)
    with _REGISTRY_LOCK:
        fold = _FOLDS.get(key)
        if fold is None or fold.identity != identity:
            fold = FindingsFold(path, identity, new_parser)
            _FOLDS.put(key, fold)
        return fold


def stream_files_count(path: Path, extract: Callable[[str], Iterable[str]]) -> int:
    """How many distinct files the stream at *path* has read so far."""
    key = str(path)
    with _REGISTRY_LOCK:
        stream = _STREAMS.get(key)
        if stream is None:
            stream = StreamFiles(path, extract)
            _STREAMS.put(key, stream)
        return stream.advance()


def clear() -> None:
    """Drop every fold (test seam)."""
    with _REGISTRY_LOCK:
        _FOLDS.clear()
        _STREAMS.clear()
