"""Standards visibility/overrides persistence for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes the per-project standards preference store
through services. Pure validation/partitioning stays importable from
``core/standards/``.
"""
from quodeq.data.fs.standards_prefs import (  # noqa: F401 — re-exported API
    collect_declared_params,
    load_project_overrides,
    load_visible_standard_ids,
    save_visible_standard_ids,
)
