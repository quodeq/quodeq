"""Standards visibility/overrides persistence for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes the per-project standards preference store
through services. Pure validation/partitioning stays importable from
``core/standards/``.
"""
from quodeq.data.fs.compiled_standards import (  # noqa: F401 — re-exported API
    iter_compiled_standards,
)
from quodeq.data.fs.standards_prefs import (  # noqa: F401 — re-exported API
    clear_project_overrides,
    save_project_overrides,
    collect_declared_params,
    load_project_overrides,
    load_visible_standard_ids,
    save_visible_standard_ids,
    visibility_is_default,
)
