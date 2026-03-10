"""Web API-backed repository for quality dimension definitions."""
from __future__ import annotations

from quodeq.adapters.web.base_repository import WebRepository


class WebDimensionsRepository(WebRepository):
    """Fetch dimension data from a remote HTTP API."""

    def list_dimensions(self) -> list[str]:
        """Retrieve all dimension names from the remote API."""
        return self._get_list("/dimensions", "dimensions")

    def get_dimension(self, dimension_id: str) -> dict:
        """Fetch a single dimension definition by ID from the remote API."""
        return self._get_dict(f"/dimensions/{dimension_id}")
