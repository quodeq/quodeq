"""Run report read access for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes run enumeration and run data reads through
services. Service-layer code imports ``data.fs.report_parser`` directly —
the layer checker, not a namespace module, is the boundary.
"""
from quodeq.data.fs.report_parser.runs import (  # noqa: F401 — re-exported API
    list_runs,
    read_run_data,
)
