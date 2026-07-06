from pathlib import Path
from collections import OrderedDict
import threading

from quodeq.core.types import DimensionResult
from quodeq.services._cache import make_lru_dimension_fetcher


def _reader_returning(score):
    def read(_root, _proj, run_id):
        return [DimensionResult(dimension="security", overall_score=score, overall_grade="Good")]
    return read


def test_different_version_is_a_separate_cache_entry():
    cache, lock = OrderedDict(), threading.Lock()
    root, proj, run = Path("/reports"), "proj", "run1"

    v1 = make_lru_dimension_fetcher(root, proj, cache, lock, 256,
                                    reader=_reader_returning("7.0/10"), version="v1")
    v2 = make_lru_dimension_fetcher(root, proj, cache, lock, 256,
                                    reader=_reader_returning("9.0/10"), version="v2")

    assert v1(run)[0].overall_score == "7.0/10"   # populates key (..., "v1")
    assert v2(run)[0].overall_score == "9.0/10"   # different version -> miss -> new read
    assert len(cache) == 2  # both versions coexist; no cross-version contamination


def test_default_version_is_backward_compatible():
    cache, lock = OrderedDict(), threading.Lock()
    fetch = make_lru_dimension_fetcher(Path("/reports"), "proj", cache, lock, 256,
                                       reader=_reader_returning("5.0/10"))
    assert fetch("run1")[0].overall_score == "5.0/10"
    assert list(cache.keys()) == [(Path("/reports"), "proj", "run1", "")]
