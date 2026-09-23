import sys

from quodeq.dashboard.cli import main, parse_args
import pytest

# The code under test sets PYTHONUTF8 / QUODEQ_WEBVIEW_TOKEN for the process;
# restore os.environ wholesale so the env-leak guard in tests/conftest.py stays green.
pytestmark = pytest.mark.usefixtures("restore_environ")


def test_default_uses_native():
    config = parse_args([])
    assert config.build.use_native is True
    assert config.build.verbose is False


def test_browser_flag_disables_native():
    config = parse_args(["--browser"])
    assert config.build.use_native is False


def test_verbose_flag():
    config = parse_args(["--verbose"])
    assert config.build.verbose is True


def test_browser_and_verbose():
    config = parse_args(["--browser", "--verbose"])
    assert config.build.use_native is False
    assert config.build.verbose is True


def test_main_catches_unexpected_exception(monkeypatch, capsys):
    monkeypatch.setattr("quodeq.dashboard.cli.run_dashboard", lambda cfg: (_ for _ in ()).throw(PermissionError("no access")))
    monkeypatch.setattr(sys, "argv", ["quodeq-dashboard"])
    exit_code = main([])
    assert exit_code == 1
    assert "Error: no access" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    lambda p: ["--evaluations", str(p)],
    lambda p: [f"--evaluations={p}"],
])
def test_evaluations_flag_counts_as_passed_in_both_spellings(tmp_path, argv):
    config = parse_args(argv(tmp_path))
    assert (config.reports_dir, config.reports_defaulted) == (tmp_path, False)


@pytest.mark.parametrize("argv", [
    lambda p: ["--static-dist", str(p)],
    lambda p: [f"--static-dist={p}"],
])
def test_static_dist_flag_counts_as_passed_in_both_spellings(tmp_path, argv):
    config = parse_args(argv(tmp_path))
    assert (config.static_dist, config.static_dist_defaulted) == (tmp_path, False)


@pytest.mark.parametrize("argv", [["--api-port=9000"], ["--api-host=example.test"], ["--api-port", "9000"]])
def test_api_flags_force_the_external_api_in_both_spellings(argv):
    assert parse_args(argv).server.api_forced is True


def test_no_flags_means_defaulted():
    config = parse_args([])
    assert (config.reports_defaulted, config.static_dist_defaulted, config.server.api_forced) == (
        True, True, False)
