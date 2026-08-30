"""Public facade for the project-identity index primitives.

``import_zip_stream`` (``api/import_project.py``) needs to read/write
``project_index.json`` and compute an identity's index key while
registering a freshly-imported project. Those primitives live in this
package's internal, leading-underscore split (``_index_io``, ``_models``,
``_resolution``); this module is the public seam so callers outside
``data/fs`` don't reach into that split directly.
"""
from __future__ import annotations

from quodeq.data.fs._index_io import _load_index as load_index, _save_index as save_index
from quodeq.data.fs._models import ProjectIdentity, ProjectRepository
from quodeq.data.fs._resolution import _index_key as index_key

__all__ = [
    "load_index",
    "save_index",
    "index_key",
    "ProjectIdentity",
    "ProjectRepository",
]
