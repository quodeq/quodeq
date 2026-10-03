"""``run_scalars`` rows carry how many findings the suppression state hid.

The Overview dashboard serves its selected run from these rows and shows
``dismissedCount`` / ``suppressedCount`` next to each gauge, so the rows must
answer that without the findings being read.
"""
from __future__ import annotations

from dataclasses import replace

from quodeq.core.types import DimensionResult
from quodeq.core.types.finding import Finding
from quodeq.data.sqlite.score_cache_rows import row_dimension, scalar_dimension
from quodeq.services.rescore import with_hidden_counts
from quodeq.services.score_cache import open_score_cache, read_cached_rows, write_cached_rows
from quodeq.services.suppression_keys import SuppressionKeys
from quodeq.services.trend_fetcher import make_rescoring_fetcher


def _finding(file: str, req: str = "S-1", principle: str = "Integrity") -> Finding:
    return Finding(practice_id=principle, req=req, file=file, line=1, snippet="x", reason="r")


def _dim(violations: list[Finding], **kw) -> DimensionResult:
    return DimensionResult(dimension="security", overall_score="6/10", overall_grade="Fair",
                           violations=violations, **kw)


def test_hidden_counts_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("QUODEQ_SCORE_CACHE_PATH", str(tmp_path / "sc.db"))
    dims = [_dim([], dismissed_count=2, suppressed_count=3), replace(_dim([]), dimension="reliability")]
    with open_score_cache() as conn:
        write_cached_rows(conn, "proj", "r1", "v1", dims)
    with open_score_cache() as conn:
        got = {d.dimension: d for d in read_cached_rows(conn, "proj", "r1", "v1")}
    assert (got["security"].dismissed_count, got["security"].suppressed_count) == (2, 3)
    # Nothing hidden reads back as None, so the serialized dimension omits the keys.
    assert got["reliability"].dismissed_count is None
    assert got["reliability"].suppressed_count is None


def test_row_dimension_keeps_the_counts_and_the_trend_shape_drops_them():
    d = _dim([_finding("a.py")], dismissed_count=1, suppressed_count=1)
    row = row_dimension(d)
    assert row.violations == [] and (row.dismissed_count, row.suppressed_count) == (1, 1)
    assert scalar_dimension(d).dismissed_count is None
    assert scalar_dimension(d).suppressed_count is None


def test_with_hidden_counts_separates_dismissals_from_deletions():
    raw = _dim([_finding("a.py"), _finding("b.py"), _finding("c.py", principle="Confidentiality")])
    keys = SuppressionKeys(
        dismissed={("S-1", "a.py", 1)},
        deleted={("security", "Confidentiality", "c.py")},
    )
    shown = replace(raw, violations=[raw.violations[1]])
    out = with_hidden_counts(raw, shown, keys)
    assert (out.dismissed_count, out.suppressed_count) == (1, 2)


def test_with_hidden_counts_is_identity_when_nothing_was_hidden():
    raw = _dim([_finding("a.py")])
    assert with_hidden_counts(raw, raw, SuppressionKeys(dismissed=set())) is raw


def test_rescoring_fetcher_annotates_hidden_counts(tmp_path):
    from quodeq.services.deleted import delete_finding
    from quodeq.services.dismissed import dismiss_finding
    project_dir = tmp_path / "proj"
    (project_dir / "r1").mkdir(parents=True)
    dismiss_finding(project_dir, {"req": "S-1", "file": "a.py", "line": 1})
    delete_finding(project_dir, {"dimension": "security", "principle": "Confidentiality", "file": "c.py"})
    raw = _dim([_finding("a.py"), _finding("b.py"), _finding("c.py", principle="Confidentiality")])
    fetch = make_rescoring_fetcher(tmp_path, "proj", base_fetcher=lambda _rid: [raw])
    (out,) = fetch("r1")
    assert len(out.violations) == 1
    assert (out.dismissed_count, out.suppressed_count) == (1, 2)
