from unittest.mock import patch

from quodeq.update import checker
from quodeq.update.source import LatestInfo
from quodeq.update.state import UpdateState, read_state, write_state


def _env(tmp_path):
    return {"QUODEQ_UPDATE_STATE_PATH": str(tmp_path / "update_state.json")}


def test_should_check_off_when_disabled(tmp_path) -> None:
    assert checker.should_check(UpdateState(auto_check_enabled=False), _env(tmp_path)) is False


def test_should_check_off_in_ci(tmp_path) -> None:
    env = {**_env(tmp_path), "CI": "true"}
    assert checker.should_check(UpdateState(), env) is False


def test_should_check_off_when_opted_out(tmp_path) -> None:
    env = {**_env(tmp_path), "QUODEQ_NO_UPDATE_NOTIFIER": "1"}
    assert checker.should_check(UpdateState(), env) is False


def test_should_check_on_when_never_checked(tmp_path) -> None:
    assert checker.should_check(UpdateState(last_check_ts=None), _env(tmp_path)) is True


def test_run_check_persists_latest(tmp_path) -> None:
    env = _env(tmp_path)
    info = LatestInfo(version="1.5.0", url="u", download_url="d", is_security=True, etag='"e"')
    with patch("quodeq.update.checker.fetch_latest", return_value=info):
        checker.run_check(env, force=True)
    state = read_state(env)
    assert state.latest_version == "1.5.0"
    assert state.is_security is True
    assert state.last_check_ts is not None


def test_run_check_is_fail_silent(tmp_path) -> None:
    env = _env(tmp_path)
    with patch("quodeq.update.checker.fetch_latest", side_effect=RuntimeError("boom")):
        checker.run_check(env, force=True)  # must not raise
    assert read_state(env).last_check_ts is not None


def test_get_status_update_available(tmp_path) -> None:
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", latest_url="u", download_url="d"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"), \
         patch("quodeq.update.channel.detect_channel", return_value="wheel"):
        status = checker.get_status(env)
    assert status["current"] == "1.4.0"
    assert status["latest"] == "9.9.9"
    assert status["update_available"] is True


def test_get_status_suppresses_dismissed(tmp_path) -> None:
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", dismissed_version="9.9.9"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"):
        status = checker.get_status(env)
    assert status["update_available"] is False


def test_dismiss_and_set_settings(tmp_path) -> None:
    env = _env(tmp_path)
    checker.dismiss("9.9.9", env)
    assert read_state(env).dismissed_version == "9.9.9"
    checker.set_settings(env, auto_check_enabled=False, disclosed=True)
    state = read_state(env)
    assert state.auto_check_enabled is False
    assert state.disclosed is True
