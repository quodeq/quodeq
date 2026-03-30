"""Service for managing standards (built-in and custom evaluators)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta

logger = logging.getLogger(__name__)


class StandardsService:
    def __init__(self, evaluators_dir: Path, compiled_dir: Path, dimensions_file: Path) -> None:
        self._evaluators_dir = evaluators_dir
        self._compiled_dir = compiled_dir
        self._dimensions_file = dimensions_file

    def list_standards(self) -> list[StandardMeta]:
        result: list[StandardMeta] = []
        result.extend(self._list_builtin())
        result.extend(self._list_custom())
        return result

    def _list_builtin(self) -> list[StandardMeta]:
        try:
            data = json.loads(self._dimensions_file.read_text())
        except (OSError, ValueError) as exc:
            logger.warning("Cannot read dimensions file: %s", exc)
            return []
        out: list[StandardMeta] = []
        for dim in data.get("applies", []):
            p_count, r_count = self._count_compiled(dim["id"])
            out.append(StandardMeta(
                id=dim["id"], name=dim.get("iso_25010", dim["id"]),
                description=f'{dim.get("source", "Built-in")} standard',
                weight=dim.get("weight", 1.0), source=dim.get("source", ""),
                type="builtin", managed=True, origin=None, origin_hash=None,
                principle_count=p_count, requirement_count=r_count,
            ))
        return out

    def _count_compiled(self, dimension_id: str) -> tuple[int, int]:
        path = self._compiled_dir / f"{dimension_id}.json"
        if not path.is_file():
            return 0, 0
        try:
            data = json.loads(path.read_text())
            principles = data.get("principles", [])
            req_count = sum(len(p.get("requirements", [])) for p in principles)
            return len(principles), req_count
        except (OSError, ValueError):
            return 0, 0

    def _list_custom(self) -> list[StandardMeta]:
        if not self._evaluators_dir.is_dir():
            return []
        out: list[StandardMeta] = []
        for path in sorted(self._evaluators_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                principles = data.get("principles", [])
                req_count = sum(len(p.get("requirements", [])) for p in principles)
                out.append(StandardMeta(
                    id=data["id"], name=data.get("name", data["id"]),
                    description=data.get("description", ""),
                    weight=data.get("weight", 1.0), source=data.get("source", ""),
                    type=data.get("type", "custom"), managed=data.get("managed", False),
                    origin=data.get("origin"), origin_hash=data.get("origin_hash"),
                    principle_count=len(principles), requirement_count=req_count,
                ))
            except (OSError, ValueError, KeyError) as exc:
                logger.warning("Skipping invalid evaluator %s: %s", path.name, exc)
        return out

    def get_standard(self, standard_id: str) -> StandardDetail:
        custom_path = self._evaluators_dir / f"{standard_id}.json"
        if custom_path.is_file():
            return self._load_detail(custom_path)
        compiled_path = self._compiled_dir / f"{standard_id}.json"
        if compiled_path.is_file():
            return self._load_builtin_detail(compiled_path, standard_id)
        raise FileNotFoundError(f"Standard not found: {standard_id}")

    def _load_detail(self, path: Path) -> StandardDetail:
        data = json.loads(path.read_text())
        return StandardDetail(
            id=data["id"], name=data.get("name", data["id"]),
            description=data.get("description", ""),
            weight=data.get("weight", 1.0), source=data.get("source", ""),
            type=data.get("type", "custom"), managed=data.get("managed", False),
            origin=data.get("origin"), origin_hash=data.get("origin_hash"),
            principles=data.get("principles", []),
        )

    def _load_builtin_detail(self, path: Path, standard_id: str) -> StandardDetail:
        data = json.loads(path.read_text())
        return StandardDetail(
            id=standard_id, name=data.get("name", standard_id),
            description=f"Built-in {data.get('name', standard_id)} standard",
            weight=self._get_builtin_weight(standard_id),
            source=", ".join(data.get("sources", [])),
            type="builtin", managed=True, origin=None, origin_hash=None,
            principles=data.get("principles", []),
        )

    def create_standard(self, data: dict) -> StandardDetail:
        standard_id = data["id"]
        self._validate_id(standard_id)
        path = self._evaluators_dir / f"{standard_id}.json"
        if path.exists():
            raise ValueError(f"Standard '{standard_id}' already exists")
        self._evaluators_dir.mkdir(parents=True, exist_ok=True)
        payload = {**data, "type": "custom", "managed": False, "origin": None, "origin_hash": None}
        path.write_text(json.dumps(payload, indent=2))
        return self._load_detail(path)

    def update_standard(self, standard_id: str, data: dict) -> StandardDetail:
        path = self._evaluators_dir / f"{standard_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Standard not found: {standard_id}")
        existing = json.loads(path.read_text())
        if existing.get("managed", False):
            raise PermissionError(f"Cannot edit managed standard '{standard_id}'")
        payload = {**data, "id": standard_id, "type": "custom", "managed": False}
        path.write_text(json.dumps(payload, indent=2))
        return self._load_detail(path)

    def delete_standard(self, standard_id: str) -> None:
        path = self._evaluators_dir / f"{standard_id}.json"
        if not path.is_file():
            if (self._compiled_dir / f"{standard_id}.json").is_file() or self._is_builtin_id(standard_id):
                raise PermissionError(f"Cannot delete built-in standard '{standard_id}'")
            raise FileNotFoundError(f"Standard not found: {standard_id}")
        existing = json.loads(path.read_text())
        if existing.get("managed", False):
            raise PermissionError(f"Cannot delete managed standard '{standard_id}'")
        path.unlink()

    def duplicate_standard(self, standard_id: str, new_id: str) -> StandardDetail:
        self._validate_id(new_id)
        new_path = self._evaluators_dir / f"{new_id}.json"
        if new_path.exists():
            raise ValueError(f"Standard '{new_id}' already exists")
        source = self.get_standard(standard_id)
        self._evaluators_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": new_id, "name": source.name, "description": source.description,
            "weight": source.weight, "source": source.source, "type": "custom",
            "managed": False, "origin": None, "origin_hash": None, "principles": source.principles,
        }
        new_path.write_text(json.dumps(payload, indent=2))
        return self._load_detail(new_path)

    def _is_builtin_id(self, standard_id: str) -> bool:
        try:
            data = json.loads(self._dimensions_file.read_text())
            return any(dim["id"] == standard_id for dim in data.get("applies", []))
        except (OSError, ValueError):
            return False

    @staticmethod
    def _validate_id(standard_id: str) -> None:
        if not standard_id or "/" in standard_id or "\\" in standard_id or ".." in standard_id:
            raise ValueError(f"Invalid standard ID: {standard_id}")

    def _get_builtin_weight(self, dimension_id: str) -> float:
        try:
            data = json.loads(self._dimensions_file.read_text())
            for dim in data.get("applies", []):
                if dim["id"] == dimension_id:
                    return dim.get("weight", 1.0)
        except (OSError, ValueError):
            pass
        return 1.0
