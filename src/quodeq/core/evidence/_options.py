"""Knobs shared by every step of the JSONL-to-Evidence parse."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from quodeq.core.evidence._refs import RefsReader
from quodeq.core.evidence.req_mapping import QuarantineSink, ReqMapReader

# A malformed-line message is handed to this sink instead of logged directly,
# so core never imports a logging framework -- see quodeq.core.observability.
MalformedLineSink = Callable[[str], None]

# Opens a JSONL file for line iteration; defaults to ``open_text``.
LineOpener = Callable[[Path], AbstractContextManager[Iterable[str]]]


@dataclass(frozen=True, slots=True)
class EvidenceParseOptions:
    """Standards lookup, reference resolution and sinks for one parse.

    Every field is optional: without readers the parse is permissive (no
    principle mapping, no compiled refs), without sinks it stays silent.
    Outer layers wire the production readers and log sinks; core itself
    performs no file I/O and no logging.
    """

    compiled_dir: Path | None = None
    evaluators_dir: Path | None = None
    req_map_reader: ReqMapReader | None = None
    refs_reader: RefsReader | None = None
    cwe_url_template: str | None = None
    on_quarantine: QuarantineSink | None = None
    on_malformed_line: MalformedLineSink | None = None
    open_fn: LineOpener | None = None
