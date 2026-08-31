"""Dimension-report I/O adapter — build and persist per-dimension report files.

Sub-modules:
  _report_constants  -- field-name constants
  _report_scoring    -- score/grade conversion and lookup building
  _report_findings   -- findings flattening and principle-row building
  _report_assembly   -- report dict assembly
  _report_io         -- disk persistence (I/O adapters)

The reader for these files lives at ``data/fs/report_parser/``.
``quodeq.analysis.report`` and its sibling ``analysis/_report_*.py`` modules
re-export this package's public names as shims, so every pre-existing
import path stays live.
"""
from __future__ import annotations
