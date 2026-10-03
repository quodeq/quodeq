from pathlib import Path
from quodeq.api.app import create_app
import pytest

# The code under test sets PYTHONUTF8 / QUODEQ_WEBVIEW_TOKEN for the process;
# restore os.environ wholesale so the env-leak guard in tests/conftest.py stays green.
pytestmark = pytest.mark.usefixtures("restore_environ")


def test_create_app_sweeps_orphaned_clones(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".quodeq" / "clones" / "orphan").mkdir(parents=True)
    (fake_home / ".quodeq" / "clones" / "orphan" / "file").write_text("x")
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    create_app()

    assert not (fake_home / ".quodeq" / "clones" / "orphan").exists()


def test_create_app_handles_missing_clones_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    # No ~/.quodeq/clones dir at all - must not raise.
    create_app()


def test_main_starts_warmup_before_serving(monkeypatch, tmp_path):
    from quodeq.api import app as app_module

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))
    started = []
    monkeypatch.setattr("quodeq.services.warmup.engine.start", started.append)
    monkeypatch.setattr("flask.Flask.run", lambda self, **kwargs: None)

    app_module.main(env={})

    assert len(started) == 1
    assert started[0].endswith("evaluations")


def test_create_app_does_not_start_warmup(monkeypatch):
    from quodeq.api.app import create_app

    started = []
    monkeypatch.setattr("quodeq.services.warmup.engine.start", started.append)
    create_app(test_config={"TESTING": True})
    assert started == []


def test_create_app_survives_a_clone_sweep_os_error(tmp_path, monkeypatch):
    """The orphaned-clone sweep's except was narrowed from bare `Exception`
    to `OSError` (R-FT-7): the realistic surface of a filesystem walk/delete.
    create_app must still finish (never block server startup on cleanup)."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    def raise_os_error(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(
        "quodeq.services.ephemeral_cleanup.sweep_orphaned_clones", raise_os_error,
    )

    create_app()  # must not raise


def test_main_survives_warmup_start_failure(monkeypatch, tmp_path):
    """_start_background_work's except was narrowed from bare `Exception` to
    (ImportError, RuntimeError, OSError); a warm-up failure must still never
    block main() from reaching _serve (its own docstring's contract)."""
    from quodeq.api import app as app_module

    monkeypatch.setenv("QUODEQ_EVALUATIONS_DIR", str(tmp_path / "evaluations"))

    def raise_os_error(*_args, **_kwargs):
        raise OSError("cache root unreadable")

    monkeypatch.setattr("quodeq.services.warmup.engine.start", raise_os_error)
    served = []
    monkeypatch.setattr("flask.Flask.run", lambda self, **kwargs: served.append(True))

    app_module.main(env={})

    assert served == [True]
