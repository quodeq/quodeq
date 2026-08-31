"""Shim: report disk persistence moved to ``data/fs/dimension_report``.

The dimension-report cluster is a filesystem I/O adapter, not analysis
logic; it now lives at ``quodeq.data.fs.dimension_report``. This module
re-exports its names so every pre-existing ``quodeq.analysis._report_io``
import path keeps working.

``os`` stays imported here (unused directly) so
``patch("quodeq.analysis._report_io.os.replace")`` keeps resolving --
it patches the one shared ``os`` module object, which the real
implementation (in ``data.fs.dimension_report._report_io``) also reads
``os.replace`` from at call time.
"""
from __future__ import annotations

import os  # noqa: F401 -- kept for the os.replace patch target above

from quodeq.data.fs.dimension_report._report_io import (  # noqa: F401
    _persist_json,
    write_dimension_report,
    write_reports,
)
