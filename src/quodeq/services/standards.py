"""Service for managing standards (built-in and custom evaluators)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from quodeq.core.types.standard import StandardDetail, StandardMeta
from quodeq.services._standards_crud import (
    create, delete, duplicate, import_from_file, update,
)
from quodeq.services._standards_io import default_read_json, default_write_json
from quodeq.services._standards_queries import (
    check_builtin_id, get_standard, list_builtin, list_custom, load_cwe_list,
)


class StandardsService:
    def __init__(self, evaluators_dir: Path, compiled_dir: Path, dimensions_file: Path,
                 read_json: Callable[[Path], dict] | None = None,
                 write_json: Callable[[Path, dict], None] | None = None) -> None:
        self._evaluators_dir = evaluators_dir
        self._compiled_dir = compiled_dir
        self._dimensions_file = dimensions_file
        self._read_json = read_json or default_read_json
        self._write_json = write_json or default_write_json

    def list_standards(self) -> list[StandardMeta]:
        return (list_builtin(self._dimensions_file, self._compiled_dir, self._read_json)
                + list_custom(self._evaluators_dir, self._read_json))

    def get_standard(self, standard_id: str) -> StandardDetail:
        return get_standard(standard_id, self._evaluators_dir, self._compiled_dir,
                            self._dimensions_file, self._read_json)

    def create_standard(self, data: dict) -> StandardDetail:
        return create(data, self._evaluators_dir, self._read_json, self._write_json)

    def update_standard(self, standard_id: str, data: dict) -> StandardDetail:
        return update(standard_id, data, self._evaluators_dir, self._read_json, self._write_json)

    def delete_standard(self, standard_id: str) -> None:
        delete(standard_id, self._evaluators_dir, self._compiled_dir,
               self._read_json,
               lambda sid: check_builtin_id(sid, self._dimensions_file, self._read_json))

    def duplicate_standard(self, standard_id: str, new_id: str) -> StandardDetail:
        return duplicate(new_id=new_id, standard_id=standard_id,
                         source_detail=self.get_standard(standard_id),
                         evaluators_dir=self._evaluators_dir,
                         read_json=self._read_json, write_json=self._write_json)

    def import_from_file(self, data: dict, force: bool = False) -> dict:
        return import_from_file(data, force, self._evaluators_dir,
                                self._read_json, self._write_json)

    def load_cwe_list(self) -> list[dict]:
        return load_cwe_list(self._compiled_dir, self._read_json)
