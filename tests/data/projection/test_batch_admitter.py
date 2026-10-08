"""A projection pass reads the installed standards once, not once per finding."""
from __future__ import annotations

from quodeq.core.admission import StandardCatalog
from quodeq.core.events.models import Judgment
from quodeq.data.projection import admission


def _judgment(i: int) -> Judgment:
    return Judgment(practice_id="P", verdict="violation", dimension="security",
                    file="a.py", line=i, reason="r")


def test_batch_admitter_reads_the_catalog_once(monkeypatch):
    calls: list[int] = []

    def counting_catalog(*_a, **_k):
        calls.append(1)
        return StandardCatalog.of([])

    monkeypatch.setattr(admission, "installed_catalog", counting_catalog)
    admit = admission.batch_admitter()
    for i in range(5):
        admit(_judgment(i))

    assert len(calls) == 1


def test_admitter_filters_each_dimension_once_per_catalog(monkeypatch):
    catalog = StandardCatalog.of([])
    filtered: list[tuple] = []
    original = StandardCatalog.only

    def counting_only(self, dims):
        filtered.append(tuple(dims))
        return original(self, dims)

    monkeypatch.setattr(StandardCatalog, "only", counting_only)
    admit = admission.make_admitter(lambda: catalog)
    for i in range(5):
        admit(_judgment(i))

    assert filtered == [("security",)]
