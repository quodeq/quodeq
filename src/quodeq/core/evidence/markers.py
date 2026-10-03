"""The ``file_done`` marker vocabulary written into a dim's evidence JSONL.

``analysis.mcp.router`` writes these markers as workers report progress;
``analysis.cache._jsonl_state``, ``analysis.cache.failure_streak`` and
``data.fs.evidence_markers`` read them back to count analysed vs abandoned
files. Lives in core (rather than ``analysis.mcp.schemas``, its original
home) so data/fs can import the vocabulary directly instead of retyping its
values -- ``tools/check_imports.py`` only allows ``data -> core``.
``analysis.mcp.schemas`` re-exports both names, so its existing importers
are unaffected.
"""
from __future__ import annotations

from enum import StrEnum


class FileDoneStatus(StrEnum):
    """``mark_file_done``'s "status" vocabulary.

    The MCP router writes these into JSONL file_done markers; the cache and
    tally readers read them back, so every side imports this rather than
    retyping the values.
    """

    OK = "ok"
    ERROR = "error"
    # Accepted by the router but deliberately absent from the tool schema's
    # enum: written by the server for files the worker could never dispatch,
    # not something a worker is told to report.
    SKIPPED = "skipped"


# The file_done JSONL entries' "_marker" value; read back alongside
# FileDoneStatus above by every reader listed in the module docstring.
JSONL_MARKER_FILE_DONE = "file_done"
