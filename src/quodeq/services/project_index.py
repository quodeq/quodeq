"""Project-identity index access for delivery layers.

The project-identity index adapter itself lives in
``data/fs/project_index.py``; the API layer does not import ``data/``
directly (see ARCHITECTURE.md import rules), so the symbols its routes
need are re-exported here — rather than api/ reaching into
``data.fs.project_index`` directly — so the api -> services -> data edge
stays visible in one place. Service-layer code imports
``quodeq.data.fs.project_index`` directly (see ``services/_wiring.py``).
"""
from quodeq.data.fs.project_index import (  # noqa: F401 — re-exported API
    ProjectIdentity,
    ProjectRepository,
    index_key,
    load_index,
    save_index,
)
