from quodeq.config.disciplines import get_valid_categories


def test_get_valid_categories_returns_defaults():
    cats = get_valid_categories()
    assert "backend" in cats
    assert isinstance(cats, frozenset)


def test_get_valid_categories_accepts_override():
    cats = get_valid_categories("alpha,beta")
    assert cats == frozenset({"alpha", "beta"})


def test_get_valid_categories_override_strips_and_filters_empty():
    # Mirrors the from_env branch's handling of the identical comma-separated
    # input shape: whitespace is stripped and empty entries are dropped.
    cats = get_valid_categories(" alpha ,, beta ,  ")
    assert cats == frozenset({"alpha", "beta"})
