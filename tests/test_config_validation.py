from codecompass.config.paths import ConfigPaths
from codecompass.config.validation import validate_evaluators


def test_validate_evaluators_reports_missing(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    (paths.evaluators_dir / "backend").mkdir(parents=True)
    result = validate_evaluators("backend", paths)
    assert result != 0
