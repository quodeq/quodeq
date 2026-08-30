from quodeq.config.disciplines import get_valid_categories


def test_get_valid_categories_returns_defaults():
    cats = get_valid_categories()
    assert "backend" in cats
    assert isinstance(cats, frozenset)


def test_get_valid_categories_accepts_override():
    cats = get_valid_categories("alpha,beta")
    assert cats == frozenset({"alpha", "beta"})
