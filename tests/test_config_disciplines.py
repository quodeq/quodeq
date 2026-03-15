from quodeq.config.disciplines import get_discipline_language, get_valid_categories, validate_new_discipline
from quodeq.config.paths import ConfigPaths


def test_validate_new_discipline_requires_name():
    assert validate_new_discipline("", "python", "backend") == 1


def test_get_valid_categories_returns_defaults():
    cats = get_valid_categories()
    assert "backend" in cats
    assert isinstance(cats, frozenset)


def test_get_valid_categories_accepts_override():
    cats = get_valid_categories("alpha,beta")
    assert cats == frozenset({"alpha", "beta"})


def test_get_discipline_language_reads_conf(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "disciplines.conf").write_text("[backend]\nlanguage=Python\ncategory=backend\n")
    paths = ConfigPaths.from_root(tmp_path)
    assert get_discipline_language("backend", paths) == "Python"
