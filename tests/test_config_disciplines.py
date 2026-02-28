from codecompass.config.disciplines import get_discipline_language, validate_new_discipline
from codecompass.config.paths import ConfigPaths


def test_validate_new_discipline_requires_name():
    assert validate_new_discipline("", "python", "backend") == 1


def test_get_discipline_language_reads_conf(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "disciplines.conf").write_text("[backend]\nlanguage=Python\ncategory=backend\n")
    paths = ConfigPaths.from_root(tmp_path)
    assert get_discipline_language("backend", paths) == "Python"
