"""Client for fetching standards from a remote GitHub-hosted library."""
from __future__ import annotations
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

class HttpClient(Protocol):
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any: ...

class UrllibJsonClient:
    def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        import urllib.request
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

class StandardsLibraryClient:
    def __init__(self, base_url: str, http_client: HttpClient, token: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._token = token

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def fetch_index(self) -> list[dict]:
        data = self._http.get_json(f"{self._base_url}/index.json", headers=self._headers())
        return data.get("standards", [])

    def fetch_standard(self, file_path: str) -> dict:
        return self._http.get_json(f"{self._base_url}/{file_path}", headers=self._headers())

    @staticmethod
    def _validate_id(standard_id: str) -> None:
        if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id:
            raise ValueError(f"Invalid standard ID from library: {standard_id}")

    def import_standard(self, file_path: str, evaluators_dir: Path) -> Path:
        if ".." in file_path:
            raise ValueError(f"Invalid library file path: {file_path}")
        data = self.fetch_standard(file_path)
        self._validate_id(data.get("id", ""))
        content_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
        evaluators_dir.mkdir(parents=True, exist_ok=True)
        dest = evaluators_dir / f"{data['id']}.json"
        # Check for collision with existing standard
        if dest.is_file():
            existing = json.loads(dest.read_text())
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
        dest.write_text(json.dumps(data, indent=2))
        return dest
