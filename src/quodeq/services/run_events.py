"""Event Log read access for delivery layers.

The API layer does not import ``data/`` directly (see ARCHITECTURE.md import
rules); this facade exposes the Event Log reader through services, mirroring
how ``services/grade_formula.py`` fronts the params store.
"""
from quodeq.data.events.reader import EventLogReader  # noqa: F401 — re-exported API
