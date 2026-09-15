"""compute_accumulated must not probe paths outside reports_root via *project*.

The project segment comes straight from the request path
(``/api/projects/<project>/accumulated``). It is resolved against the
directory listing, so a traversal or absolute segment is simply "not found"
and never touches the filesystem outside the reports tree.
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.scoring.params import DEFAULT_PARAMS
from quodeq.services.accumulated import compute_accumulated
from tests.services._accumulated_fixtures import _dim, _setup_project


def _reports_root(tmp_path: Path) -> Path:
    return _setup_project(tmp_path, "proj", [("run1", [_dim("maintainability", "8.0", "A")])])


def test_traversal_project_segment_is_reported_as_not_found(tmp_path: Path) -> None:
    reports_root = _reports_root(tmp_path)
    (tmp_path / "escape").mkdir()  # exists, but outside reports_root
    assert compute_accumulated(str(reports_root), "../escape", None, params=DEFAULT_PARAMS) is None


def test_absolute_project_segment_is_reported_as_not_found(tmp_path: Path) -> None:
    reports_root = _reports_root(tmp_path)
    assert compute_accumulated(str(reports_root), str(tmp_path), None, params=DEFAULT_PARAMS) is None


def test_real_project_still_resolves(tmp_path: Path) -> None:
    reports_root = _reports_root(tmp_path)
    result = compute_accumulated(str(reports_root), "proj", None, params=DEFAULT_PARAMS)
    assert result is not None
    assert result["project"] == "proj"
