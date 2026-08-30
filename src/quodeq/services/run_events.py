"""Event Log read access for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes the Event Log reader through services, mirroring
how ``services/grade_formula.py`` fronts the params store.
"""
from quodeq.data.events.reader import EventLogReader  # noqa: F401 — re-exported API
from quodeq.services.ports import read_dimensions  # noqa: F401,E402 — re-exported API


def read_run_dim_states(reports_dir, project: str, run_id: str) -> dict:
    """Per-dimension state map for a run, addressed by identifiers.

    The api layer used to compose ``reports_dir / project / run_id`` itself;
    it now passes identifiers and this facade owns the storage path. Empty
    dict when the run has no (or an unreadable) dimensions file. Raises
    ValueError on traversal segments — the join happens here now, so the
    guard belongs here too.
    """
    from pathlib import Path  # noqa: PLC0415

    from quodeq.shared.validation import validate_path_segment  # noqa: PLC0415

    validate_path_segment(project, run_id)
    run_dir = Path(reports_dir) / project / run_id
    return read_dimensions(run_dir).get("dimensions", {})
