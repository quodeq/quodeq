from pathlib import Path

import codecompass.config.paths as paths_module
from codecompass.evaluate.runner import EvaluateConfig, run


def test_evaluate_uses_project_root_for_mappings(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    reports = tmp_path / "reports"
    reports.mkdir()

    monkeypatch.setattr("codecompass.evaluate.runner.run_dimensions", lambda *_args, **_kwargs: (1, 0))

    config = EvaluateConfig(
        discipline="cli_bash",
        repo=str(repo),
        reports_dir=reports,
        reports_defaulted=False,
    )

    result = run(config)

    assert result == 0


def test_evaluate_from_nested_cwd(monkeypatch, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    nested_cwd = project_root / "ui" / "server"
    fake_installed_module_path = project_root / ".venv" / "lib" / "python3.14" / "site-packages" / "codecompass" / "config" / "paths.py"

    monkeypatch.setattr(paths_module, "__file__", str(fake_installed_module_path))
    monkeypatch.chdir(nested_cwd)

    monkeypatch.setattr("codecompass.evaluate.runner.run_dimensions", lambda *_args, **_kwargs: (1, 0))

    repo = tmp_path / "repo"
    repo.mkdir()
    reports = tmp_path / "reports"
    reports.mkdir()

    config = EvaluateConfig(
        discipline="cli_bash",
        repo=str(repo),
        reports_dir=reports,
        reports_defaulted=False,
    )

    result = run(config)

    assert result == 0
