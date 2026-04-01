"""Service for managing standards (built-in and custom evaluators)."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta
from quodeq.services.import_validator import validate_import, scan_injection

logger = logging.getLogger(__name__)

_TYPE_CUSTOM = "custom"
_TYPE_BUILTIN = "builtin"
_TYPE_MANAGED = "managed"


def _default_read_json(path: Path) -> dict:
    """Read and parse a JSON file."""
    return json.loads(path.read_text())


def _default_write_json(path: Path, data: dict) -> None:
    """Serialize *data* to JSON and write it to *path*."""
    path.write_text(json.dumps(data, indent=2))


def _count_principles_and_requirements(data: dict) -> tuple[int, int]:
    """Return (principle_count, requirement_count) from a standard's JSON data."""
    principles = data.get("principles", [])
    req_count = sum(len(p.get("requirements", [])) for p in principles)
    return len(principles), req_count


class StandardsService:
    def __init__(
        self, evaluators_dir: Path, compiled_dir: Path, dimensions_file: Path,
        read_json: Callable[[Path], dict] | None = None,
        write_json: Callable[[Path, dict], None] | None = None,
    ) -> None:
        self._evaluators_dir = evaluators_dir
        self._compiled_dir = compiled_dir
        self._dimensions_file = dimensions_file
        self._read_json = read_json or _default_read_json
        self._write_json = write_json or _default_write_json

    def list_standards(self) -> list[StandardMeta]:
        """Return all standards (built-in and custom) as metadata entries."""
        result: list[StandardMeta] = []
        result.extend(self._list_builtin())
        result.extend(self._list_custom())
        return result

    def _list_builtin(self) -> list[StandardMeta]:
        try:
            data = self._read_json(self._dimensions_file)
        except (OSError, ValueError) as exc:
            logger.warning("Cannot read dimensions file: %s", exc)
            return []
        out: list[StandardMeta] = []
        for dim in data.get("applies", []):
            p_count, r_count = self._count_compiled(dim["id"])
            dim_type = dim.get("type", _TYPE_BUILTIN)
            out.append(StandardMeta(
                id=dim["id"], name=dim.get("iso_25010") or dim.get("name", dim["id"]),
                description=f'{dim.get("source", "Built-in")} standard',
                weight=dim.get("weight", 1.0), source=dim.get("source", ""),
                type=dim_type, managed=True, origin=None, origin_hash=None,
                principle_count=p_count, requirement_count=r_count,
            ))
        return out

    def _count_compiled(self, dimension_id: str) -> tuple[int, int]:
        path = self._compiled_dir / f"{dimension_id}.json"
        if not path.is_file():
            return 0, 0
        try:
            data = self._read_json(path)
            return _count_principles_and_requirements(data)
        except (OSError, ValueError):
            return 0, 0

    def _list_custom(self) -> list[StandardMeta]:
        if not self._evaluators_dir.is_dir():
            return []
        out: list[StandardMeta] = []
        for path in sorted(self._evaluators_dir.glob("*.json")):
            try:
                data = self._read_json(path)
                p_count, r_count = _count_principles_and_requirements(data)
                out.append(StandardMeta(
                    id=data["id"], name=data.get("name", data["id"]),
                    description=data.get("description", ""),
                    weight=data.get("weight", 1.0), source=data.get("source", ""),
                    type=data.get("type", _TYPE_CUSTOM), managed=data.get("managed", False),
                    origin=data.get("origin"), origin_hash=data.get("origin_hash"),
                    principle_count=p_count, requirement_count=r_count,
                ))
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("Skipping invalid evaluator %s: %s", path.name, exc)
        return out

    def get_standard(self, standard_id: str) -> StandardDetail:
        """Return full detail for a single standard, checking custom then built-in."""
        custom_path = self._evaluators_dir / f"{standard_id}.json"
        if custom_path.is_file():
            return self._load_detail(custom_path)
        compiled_path = self._compiled_dir / f"{standard_id}.json"
        if compiled_path.is_file():
            return self._load_builtin_detail(compiled_path, standard_id)
        raise FileNotFoundError(f"Standard not found: {standard_id}")

    def _load_detail(self, path: Path) -> StandardDetail:
        data = self._read_json(path)
        return StandardDetail(
            id=data["id"], name=data.get("name", data["id"]),
            description=data.get("description", ""),
            weight=data.get("weight", 1.0), source=data.get("source", ""),
            type=data.get("type", _TYPE_CUSTOM), managed=data.get("managed", False),
            origin=data.get("origin"), origin_hash=data.get("origin_hash"),
            principles=data.get("principles", []),
        )

    def _load_builtin_detail(self, path: Path, standard_id: str) -> StandardDetail:
        data = self._read_json(path)
        dim_type = data.get("type", _TYPE_BUILTIN)
        source = data.get("source", "") or ", ".join(data.get("sources", []))
        return StandardDetail(
            id=standard_id, name=data.get("name", standard_id),
            description=f"{data.get('name', standard_id)} standard",
            weight=self._get_builtin_weight(standard_id),
            source=source,
            type=dim_type, managed=True, origin=None, origin_hash=None,
            principles=data.get("principles", []),
        )

    def create_standard(self, data: dict) -> StandardDetail:
        """Create a new custom standard from *data* and persist it to disk."""
        standard_id = data["id"]
        self._validate_id(standard_id)
        path = self._evaluators_dir / f"{standard_id}.json"
        if path.exists():
            raise ValueError(f"Standard '{standard_id}' already exists")
        self._evaluators_dir.mkdir(parents=True, exist_ok=True)
        payload = {**data, "type": _TYPE_CUSTOM, "managed": False, "origin": None, "origin_hash": None}
        self._write_json(path, payload)
        return self._load_detail(path)

    def update_standard(self, standard_id: str, data: dict) -> StandardDetail:
        """Update an existing custom standard with new *data*."""
        path = self._evaluators_dir / f"{standard_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Standard not found: {standard_id}")
        existing = self._read_json(path)
        if existing.get("managed", False):
            raise PermissionError(f"Cannot edit managed standard '{standard_id}'")
        payload = {**data, "id": standard_id, "type": _TYPE_CUSTOM, "managed": False}
        self._write_json(path, payload)
        return self._load_detail(path)

    def delete_standard(self, standard_id: str) -> None:
        """Delete a custom standard. Raises for built-in or managed standards."""
        path = self._evaluators_dir / f"{standard_id}.json"
        if not path.is_file():
            if (self._compiled_dir / f"{standard_id}.json").is_file() or self._is_builtin_id(standard_id):
                raise PermissionError(f"Cannot delete built-in standard '{standard_id}'")
            raise FileNotFoundError(f"Standard not found: {standard_id}")
        existing = self._read_json(path)
        if existing.get("managed", False):
            raise PermissionError(f"Cannot delete managed standard '{standard_id}'")
        path.unlink()

    def duplicate_standard(self, standard_id: str, new_id: str) -> StandardDetail:
        """Duplicate an existing standard under *new_id* as a custom copy."""
        self._validate_id(new_id)
        new_path = self._evaluators_dir / f"{new_id}.json"
        if new_path.exists():
            raise ValueError(f"Standard '{new_id}' already exists")
        source = self.get_standard(standard_id)
        self._evaluators_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": new_id, "name": source.name, "description": source.description,
            "weight": source.weight, "source": source.source, "type": _TYPE_CUSTOM,
            "managed": False, "origin": None, "origin_hash": None, "principles": source.principles,
        }
        self._write_json(new_path, payload)
        return self._load_detail(new_path)

    def import_from_file(self, data: dict, force: bool = False) -> dict:
        """Import an evaluator from parsed file data.

        Returns a dict with keys:
        - ``status``: ``"imported"`` or ``"conflict"``
        - ``detail``: :class:`StandardDetail` (on success) or ``None``
        - ``existing``: existing :class:`StandardMeta` (on conflict) or ``None``
        - ``warnings``: list of injection scan warnings
        """
        validation = validate_import(data)
        if not validation["valid"]:
            raise ValueError("; ".join(validation["errors"]))

        cleaned = validation["data"]
        standard_id = cleaned["id"]
        warnings = scan_injection(cleaned)

        path = self._evaluators_dir / f"{standard_id}.json"
        if path.is_file() and not force:
            existing = self._read_json(path)
            principles = existing.get("principles", [])
            req_count = sum(len(p.get("requirements", [])) for p in principles)
            return {
                "status": "conflict",
                "detail": None,
                "existing": StandardMeta(
                    id=existing["id"], name=existing.get("name", existing["id"]),
                    description=existing.get("description", ""),
                    weight=existing.get("weight", 1.0), source=existing.get("source", ""),
                    type=existing.get("type", _TYPE_CUSTOM), managed=existing.get("managed", False),
                    origin=existing.get("origin"), origin_hash=existing.get("origin_hash"),
                    principle_count=len(principles), requirement_count=req_count,
                ),
                "warnings": warnings,
            }

        if path.is_file() and force:
            existing_data = self._read_json(path)
            if existing_data.get("managed", False):
                raise PermissionError(f"Cannot overwrite managed standard '{standard_id}'")

        self._evaluators_dir.mkdir(parents=True, exist_ok=True)
        payload = {**cleaned, "type": _TYPE_CUSTOM, "managed": False, "origin": None, "origin_hash": None}
        self._write_json(path, payload)
        detail = self._load_detail(path)

        return {"status": "imported", "detail": detail, "existing": None, "warnings": warnings}

    def _is_builtin_id(self, standard_id: str) -> bool:
        try:
            data = self._read_json(self._dimensions_file)
            return any(dim["id"] == standard_id for dim in data.get("applies", []))
        except (OSError, ValueError):
            return False

    @staticmethod
    def _validate_id(standard_id: str) -> None:
        if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id:
            raise ValueError(f"Invalid standard ID: {standard_id}")

    def load_cwe_list(self) -> list[dict]:
        """Load the CWE reference list from the compiled standards directory."""
        cwe_path = self._compiled_dir.parent / "cwe" / "audit.json"
        if not cwe_path.is_file():
            return []
        try:
            entries = self._read_json(cwe_path)
            return [
                {"id": e["id"], "name": e["name"],
                 "abstraction": e.get("abstraction", ""),
                 "dimensions": e.get("dimensions", [])}
                for e in entries
            ]
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("Cannot read CWE list: %s", exc)
            return []

    def _get_builtin_weight(self, dimension_id: str) -> float:
        try:
            data = self._read_json(self._dimensions_file)
            for dim in data.get("applies", []):
                if dim["id"] == dimension_id:
                    return dim.get("weight", 1.0)
        except (OSError, ValueError):
            pass
        return 1.0
