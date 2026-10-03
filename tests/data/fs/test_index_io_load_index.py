"""``load_index``: a corrupt or non-object ``project_index.json`` must
degrade to ``{}``, matching every other index/registry reader in this
package (``read_json_object``'s contract), not surface the raw parsed
value to callers that index into it as ``dict[str, str]``.
"""
from __future__ import annotations

from quodeq.data.fs.project_index import load_index


def test_missing_file_returns_empty(tmp_path):
    assert load_index(tmp_path) == {}


def test_corrupt_json_returns_empty(tmp_path):
    (tmp_path / "project_index.json").write_text("{ not valid json")
    assert load_index(tmp_path) == {}


def test_non_object_json_returns_empty(tmp_path):
    """A syntactically-valid but non-object index (e.g. a JSON array) must
    not be handed back as-is: callers do ``key in index`` / ``index[key]``
    / ``del index[key]``, which misbehave or crash on a list."""
    (tmp_path / "project_index.json").write_text("[1, 2, 3]")
    assert load_index(tmp_path) == {}


def test_valid_index_still_loads(tmp_path):
    (tmp_path / "project_index.json").write_text('{"proj-a": "uuid-1"}')
    assert load_index(tmp_path) == {"proj-a": "uuid-1"}
