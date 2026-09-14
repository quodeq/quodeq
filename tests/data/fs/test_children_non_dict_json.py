"""Cluster 24 (R-FT-2) — find_children's non-dict JSON crash.

``find_children`` used to run ``json.loads(...).get("parent")`` on each
project's ``repository_info.json``. A file that is valid JSON but not a JSON
object (``[]``, ``null``, a bare string, from a partial write or hand-edit)
made ``.get`` raise ``AttributeError``, which was outside the
``except (json.JSONDecodeError, OSError)`` clause and aborted the whole
``reports_root.iterdir()`` loop -- one corrupted project took down the entire
project listing.

Fixed by routing through ``quodeq.core.utils.io.read_json``, which raises
``ValueError`` for both parse/read failures and non-dict payloads, and
narrowing the except clause to that single type.
"""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.data.fs.children import find_children


def _make_project(root: Path, name: str, repository_info) -> None:
    project_dir = root / name
    project_dir.mkdir()
    info_path = project_dir / "repository_info.json"
    info_path.write_text(json.dumps(repository_info), encoding="utf-8")


def test_find_children_skips_list_payload_and_returns_valid_siblings(tmp_path: Path):
    """A bare `[]` (valid JSON, not a dict) is skipped; valid siblings, some
    before and some after it in iteration, are still returned."""
    _make_project(tmp_path, "aaa-before", {"parent": "parent-1"})
    _make_project(tmp_path, "mmm-corrupt", [])
    _make_project(tmp_path, "zzz-after", {"parent": "parent-1"})

    result = find_children(tmp_path, "parent-1")

    assert sorted(result) == ["aaa-before", "zzz-after"]
    assert "mmm-corrupt" not in result


def test_find_children_skips_null_payload_and_returns_valid_siblings(tmp_path: Path):
    """A bare `null` (valid JSON, not a dict) is skipped; the valid sibling is
    still returned -- proving the loop continues, not just that it doesn't
    throw."""
    _make_project(tmp_path, "corrupt-null", None)
    _make_project(tmp_path, "valid-sibling", {"parent": "parent-1"})

    result = find_children(tmp_path, "parent-1")

    assert result == ["valid-sibling"]


def test_find_children_skips_string_payload_and_returns_valid_siblings(tmp_path: Path):
    """A bare JSON string (valid JSON, not a dict) is skipped; the valid
    sibling is still returned."""
    _make_project(tmp_path, "corrupt-string", "not-an-object")
    _make_project(tmp_path, "valid-sibling", {"parent": "parent-1"})

    result = find_children(tmp_path, "parent-1")

    assert result == ["valid-sibling"]


def test_find_children_skips_malformed_json_and_returns_valid_siblings(tmp_path: Path):
    """A genuinely malformed (undecodable) JSON file is still skipped, same
    as before this fix -- the widened except must not regress the original
    JSONDecodeError/OSError coverage."""
    corrupt_dir = tmp_path / "corrupt-malformed"
    corrupt_dir.mkdir()
    (corrupt_dir / "repository_info.json").write_text("{not valid json", encoding="utf-8")
    _make_project(tmp_path, "valid-sibling", {"parent": "parent-1"})

    result = find_children(tmp_path, "parent-1")

    assert result == ["valid-sibling"]
