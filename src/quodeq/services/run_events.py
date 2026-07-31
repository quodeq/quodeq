"""Event Log read access for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes the Event Log reader through services, mirroring
how ``services/grade_formula.py`` fronts the params store.
"""
from quodeq.data.events.reader import EventLogReader  # noqa: F401 — re-exported API
from quodeq.data.fs.dimensions_state_store import read_dimensions  # noqa: F401,E402 — re-exported API
