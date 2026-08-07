"""api passes identifiers, not constructed paths, for run dimension states."""
from __future__ import annotations

import json


def test_read_run_dim_states_returns_dimensions_map(tmp_path):
    from quodeq.services.run_events import read_run_dim_states

    run_dir = tmp_path / "proj" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "dimensions.json").write_text(
        json.dumps({"dimensions": {"security": {"state": "done"}}}), encoding="utf-8",
    )

    assert read_run_dim_states(tmp_path, "proj", "run-1") == {
        "security": {"state": "done"},
    }


def test_read_run_dim_states_missing_run_is_empty(tmp_path):
    from quodeq.services.run_events import read_run_dim_states

    assert read_run_dim_states(tmp_path, "proj", "nope") == {}


def test_read_run_dim_states_rejects_traversal(tmp_path):
    import pytest

    from quodeq.services.run_events import read_run_dim_states

    with pytest.raises(ValueError):
        read_run_dim_states(tmp_path, "../etc", "run-1")


def test_api_builds_no_run_paths():
    """_read_dim_states hands identifiers to the facade instead of joining
    a run_dir itself (the api layer must not compose storage paths)."""
    from quodeq.api import _evaluation_routes as routes

    src = open(routes.__file__).read()
    assert "_reports_dir()) / project / run_id" not in src
