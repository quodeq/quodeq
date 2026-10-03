"""rescore_runs_by_dimension reads the project's suppression rules once."""
from __future__ import annotations

from quodeq.services import scoring
from quodeq.services.suppression_keys import SuppressionKeys


def _stub(monkeypatch) -> list[object]:
    loads: list[object] = []

    def counting_load(project_dir):
        loads.append(project_dir)
        return ()

    monkeypatch.setattr("quodeq.services.scoring._rescoring.load_suppression_rules", counting_load)
    monkeypatch.setattr(
        "quodeq.services.scoring._rescoring.make_run_dimension_fetcher",
        lambda root, project: (lambda run_id: [{"dimension": run_id}]),
    )
    monkeypatch.setattr(
        "quodeq.services.scoring._rescoring.rescore_dimensions",
        lambda dims, keys, params=None, run_dir=None: {"dimensions": dims},
    )
    return loads


def test_rules_are_loaded_once_for_many_runs(tmp_path, monkeypatch):
    loads = _stub(monkeypatch)
    dims = [{"dimension": d, "runId": d} for d in ("security", "reliability", "usability")]

    out = scoring.rescore_runs_by_dimension(
        dims, tmp_path, "proj", SuppressionKeys(dismissed=frozenset()))

    assert loads == [tmp_path / "proj"]
    assert sorted(out) == ["reliability", "security", "usability"]


def test_no_runs_means_no_rules_read(tmp_path, monkeypatch):
    loads = _stub(monkeypatch)
    scoring.rescore_runs_by_dimension([], tmp_path, "proj", SuppressionKeys(dismissed=frozenset()))
    assert loads == []
