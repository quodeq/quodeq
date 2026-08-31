"""Client for fetching standards from a remote GitHub-hosted library."""
from __future__ import annotations
import hashlib
import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from quodeq.services._wiring import (
    read_standard_payload, resolve_jailed_standard_path, write_standard_payload,
)

_HTTP_TIMEOUT_S = 30
_HASH_PREFIX_LEN = 16

class HttpClient(Protocol):
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any: ...

class UrllibJsonClient:
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        req = urllib.request.Request(url, headers=headers or {})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S, context=ctx) as resp:
            return json.loads(resp.read())

class StandardsLibraryClient:
    def __init__(self, base_url: str, http_client: HttpClient, token: str | None = None) -> None:
        if not base_url.startswith("https://"):
            raise ValueError(f"Only https:// base URLs are allowed, got: {base_url!r}")
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._token = token

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def fetch_index(self) -> list[dict]:
        """Retrieve the remote standards library index."""
        data = self._http.get_json(f"{self._base_url}/index.json", headers=self._headers())
        return data.get("standards", [])

    def fetch_standard(self, file_path: str) -> dict:
        """Download a single standard JSON by its library file path."""
        return self._http.get_json(f"{self._base_url}/{file_path}", headers=self._headers())

    @staticmethod
    def _validate_id(standard_id: str) -> None:
        if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id:
            raise ValueError(f"Invalid standard ID from library: {standard_id}")

    def import_standard(self, file_path: str, evaluators_dir: Path) -> Path:
        """Fetch a remote standard and save it locally as a managed evaluator."""
        if ".." in file_path:
            raise ValueError(f"Invalid library file path: {file_path}")
        data = self.fetch_standard(file_path)
        self._validate_id(data.get("id", ""))
        content_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:_HASH_PREFIX_LEN]
        try:
            dest = resolve_jailed_standard_path(evaluators_dir, data["id"])
        except ValueError:
            raise ValueError(f"Invalid standard ID from library: {data['id']}") from None
        # Check for collision with existing standard
        existing = read_standard_payload(dest)
        if existing is not None:
            if existing.get("origin") == file_path:
                # Same origin — update in place
                pass
            else:
                raise ValueError(
                    f"A standard with ID '{data['id']}' already exists "
                    f"from a different source. Duplicate to customize it first, "
                    f"or delete the existing one."
                )
        data["type"] = "community"
        data["managed"] = True
        data["origin"] = file_path
        data["origin_hash"] = content_hash
        write_standard_payload(dest, data)
        return dest
