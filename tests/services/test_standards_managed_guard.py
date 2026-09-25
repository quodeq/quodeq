"""The shared standards guards keep each call site's own wording.

Update, delete and forced import all refuse a managed standard through one
guard that names the refused action; create and duplicate both refuse a
taken id through one guard.
"""
from __future__ import annotations

import json

import pytest

from quodeq.services.standards import StandardsService

_MANAGED = {"id": "managed-one", "name": "Managed", "managed": True, "type": "community", "principles": []}


@pytest.fixture()
def service(tmp_path):
    evaluators = tmp_path / "evaluators"
    evaluators.mkdir()
    (evaluators / "managed-one.json").write_text(json.dumps(_MANAGED))
    compiled = tmp_path / "compiled"
    compiled.mkdir()
    dimensions = tmp_path / "dimensions.json"
    dimensions.write_text(json.dumps({"applies": []}))
    return StandardsService(evaluators_dir=evaluators, compiled_dir=compiled, dimensions_file=dimensions)


def test_update_names_the_edit_action(service):
    with pytest.raises(PermissionError, match=r"^Cannot edit managed standard 'managed-one'$"):
        service.update_standard("managed-one", {**_MANAGED, "name": "Changed"})


def test_delete_names_the_delete_action(service):
    with pytest.raises(PermissionError, match=r"^Cannot delete managed standard 'managed-one'$"):
        service.delete_standard("managed-one")


def test_forced_import_names_the_overwrite_action(service):
    data = {"id": "managed-one", "name": "Override", "principles": []}
    with pytest.raises(PermissionError, match=r"^Cannot overwrite managed standard 'managed-one'$"):
        service.import_from_file(data, force=True)


def test_duplicate_onto_a_taken_id_is_refused_like_create(service):
    with pytest.raises(ValueError, match=r"^Standard 'managed-one' already exists$"):
        service.duplicate_standard("managed-one", "managed-one")
