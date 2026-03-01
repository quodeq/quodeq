from pathlib import Path

from codecompass.evaluate.runner import EvaluateConfig, run


def test_evaluate_autodetects_discipline(monkeypatch, tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')

    reports = tmp_path / "reports"

    monkeypatch.setattr(
        "codecompass.evaluate.runner.detect_discipline",
        lambda *_args, **_kwargs: "frontend_react",
    )
    monkeypatch.setattr("codecompass.evaluate.runner.prepare_repository", lambda path: path)
    monkeypatch.setattr("codecompass.evaluate.runner.run_dimensions", lambda *_args, **_kwargs: (1, 0))
    monkeypatch.setattr(
        "codecompass.evaluate.runner.list_available_dimensions",
        lambda *_args, **_kwargs: ["maintainability"],
    )
    monkeypatch.setattr(
        "codecompass.evaluate.runner.resolve_dimension_selection",
        lambda *_args, **_kwargs: (["maintainability"], []),
    )

    config = EvaluateConfig(
        discipline=None,
        repo=str(repo),
        reports_dir=reports,
        reports_defaulted=True,
    )

    result = run(config)
    assert result == 0
