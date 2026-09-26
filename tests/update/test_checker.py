import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

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


@pytest.mark.parametrize("exc", [AttributeError("boom"), TypeError("boom")])
def test_run_check_is_fail_silent_for_the_narrowed_tuple(tmp_path, exc) -> None:
    """A malformed-JSON leak from fetch_latest (e.g. a list item where a dict
    was expected) is caught; the attempt timestamp is still persisted."""
    env = _env(tmp_path)
    with patch("quodeq.update.checker.fetch_latest", side_effect=exc):
        checker.run_check(env, force=True)  # must not raise
    assert read_state(env).last_check_ts is not None


def test_run_check_propagates_an_unexpected_error_but_still_persists_the_attempt(tmp_path) -> None:
    """R-FT-7 -- an error outside (AttributeError, TypeError) must propagate.
    Review fix: fetch_latest can raise something outside that tuple too (e.g.
    httpx.InvalidURL); the attempt must still be persisted -- it is written
    BEFORE the network call now, not from inside this narrowed except."""
    env = _env(tmp_path)
    with patch("quodeq.update.checker.fetch_latest", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError, match="boom"):
            checker.run_check(env, force=True)
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


def test_get_status_includes_self_update(tmp_path) -> None:
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", download_url="d"), env)
    with patch(
        "quodeq.update.selfupdate.describe",
        return_value={"supported": False, "reason": "not_frozen", "phase": "idle"},
    ) as describe:
        status = checker.get_status(env)
    describe.assert_called_once_with("d")
    assert status["self_update"]["reason"] == "not_frozen"


def test_get_status_suppresses_dismissed(tmp_path) -> None:
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", dismissed_version="9.9.9"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"):
        status = checker.get_status(env)
    assert status["update_available"] is False


def test_get_status_survives_a_type_corrupt_latest_version(tmp_path) -> None:
    """A numeric latest_version in update_state.json used to raise
    AttributeError inside is_newer's normalize() (an int has no .strip()),
    which escaped get_status and, from there, cli.py's
    maybe_emit_cli_notice after every command. The corrupt field is now
    dropped on read, so get_status must not raise."""
    env = _env(tmp_path)
    Path(env["QUODEQ_UPDATE_STATE_PATH"]).write_text(json.dumps({"latest_version": 5}))
    status = checker.get_status(env)
    assert status["latest"] is None
    assert status["update_available"] is False


def test_dismiss_and_set_settings(tmp_path) -> None:
    env = _env(tmp_path)
    checker.dismiss("9.9.9", env)
    assert read_state(env).dismissed_version == "9.9.9"
    checker.set_settings(env, auto_check_enabled=False, disclosed=True)
    state = read_state(env)
    assert state.auto_check_enabled is False
    assert state.disclosed is True


def test_should_check_false_when_checked_recently(tmp_path) -> None:
    """should_check returns False when last_check_ts is within the interval."""
    env = _env(tmp_path)
    state = UpdateState(last_check_ts=datetime.now(timezone.utc).isoformat())
    assert checker.should_check(state, env) is False


def test_run_check_handles_not_modified(tmp_path) -> None:
    """run_check on a 304 not_modified response leaves latest_version unchanged and updates etag."""
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="1.2.3", etag='"old"'), env)
    not_modified = LatestInfo(not_modified=True, etag='"new"')
    with patch("quodeq.update.checker.fetch_latest", return_value=not_modified):
        checker.run_check(env, force=True)
    state = read_state(env)
    assert state.latest_version == "1.2.3"
    assert state.etag == '"new"'
    assert state.last_check_ts is not None


def test_interval_falls_back_on_invalid_value(tmp_path) -> None:
    """_interval returns default when the env var is not a valid int."""
    env = {**_env(tmp_path), "QUODEQ_UPDATE_CHECK_INTERVAL": "not-a-number"}
    # should_check still returns True (never checked) — exercises _interval ValueError path
    state = UpdateState(last_check_ts=None)
    assert checker.should_check(state, env) is True


def test_should_check_invalid_timestamp_returns_true(tmp_path) -> None:
    """should_check returns True when last_check_ts is unparseable."""
    env = _env(tmp_path)
    state = UpdateState(last_check_ts="not-a-date")
    assert checker.should_check(state, env) is True


def test_should_check_naive_timestamp_returns_true(tmp_path) -> None:
    """Review fix -- a naive (no tzinfo) last_check_ts makes the aware-minus-
    naive subtraction raise TypeError, which used to escape should_check and
    500 the /api/update/check route. Now counts as 'due', per the docstring."""
    env = _env(tmp_path)
    state = UpdateState(last_check_ts="2026-01-01T00:00:00")
    assert checker.should_check(state, env) is True


def test_run_check_skips_write_when_gated_out(tmp_path) -> None:
    """run_check returns without writing state when should_check is False."""
    env = _env(tmp_path)
    state_before = read_state(env)
    ts_before = state_before.last_check_ts
    with patch("quodeq.update.checker.should_check", return_value=False):
        checker.run_check(env)
    assert read_state(env).last_check_ts == ts_before


def test_run_check_handles_none_from_fetch(tmp_path) -> None:
    """run_check persists last_check_ts when fetch_latest returns None."""
    env = _env(tmp_path)
    with patch("quodeq.update.checker.fetch_latest", return_value=None):
        checker.run_check(env, force=True)
    assert read_state(env).last_check_ts is not None


def test_begin_self_update_no_update_available(tmp_path) -> None:
    """begin_self_update rejects when no update is available."""
    env = _env(tmp_path)
    result = checker.begin_self_update(env)
    assert result == {"ok": False, "code": "NO_UPDATE", "error": "no update available"}


def test_begin_self_update_unsupported(tmp_path) -> None:
    """begin_self_update rejects with the self_update.describe() reason when unsupported."""
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", download_url="d"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"), patch(
        "quodeq.update.selfupdate.describe",
        return_value={"supported": False, "reason": "not_frozen", "phase": "idle"},
    ):
        result = checker.begin_self_update(env)
    assert result == {
        "ok": False,
        "code": "UNSUPPORTED",
        "error": "self-update is not supported here",
        "reason": "not_frozen",
    }


def test_begin_self_update_busy(tmp_path) -> None:
    """begin_self_update rejects when selfupdate.start() reports one is already running."""
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", download_url="d"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"), patch(
        "quodeq.update.selfupdate.describe",
        return_value={"supported": True, "reason": None, "phase": "idle"},
    ), patch("quodeq.update.checker._selfupdate.start", return_value=False):
        result = checker.begin_self_update(env)
    assert result == {"ok": False, "code": "BUSY", "error": "self-update already running"}


def test_begin_self_update_starts(tmp_path) -> None:
    """begin_self_update kicks off the update and returns fresh status on success."""
    env = _env(tmp_path)
    write_state(UpdateState(latest_version="9.9.9", download_url="d"), env)
    with patch("quodeq.update.checker.__version__", "1.4.0"), patch(
        "quodeq.update.selfupdate.describe",
        return_value={"supported": True, "reason": None, "phase": "idle"},
    ), patch("quodeq.update.checker._selfupdate.start", return_value=True) as start:
        result = checker.begin_self_update(env)
    start.assert_called_once_with("d", "9.9.9")
    assert result["ok"] is True
    assert result["status"]["latest"] == "9.9.9"


def test_check_async_invokes_run_check(tmp_path) -> None:
    """check_async starts a thread that calls run_check."""
    env = _env(tmp_path)
    called_with = []

    class _FakeThread:
        def __init__(self, target, args=(), daemon=False):
            self._target = target
            self._args = args

        def start(self):
            self._target(*self._args)

    with patch("quodeq.update.checker.threading.Thread", _FakeThread), \
         patch("quodeq.update.checker.run_check", side_effect=lambda *a, **kw: called_with.append(a)):
        checker.check_async(env)

    assert len(called_with) == 1
    assert called_with[0] == (env,)


def test_check_async_thread_survives_a_run_check_failure(tmp_path, caplog) -> None:
    """R-FT-7 -- the run_isolated boundary at the thread target: an exception
    from run_check itself (e.g. an unexpected fetch_latest bug) is logged and
    does not escape as an unhandled exception on the daemon thread."""
    env = _env(tmp_path)

    class _SyncThread:
        def __init__(self, target, daemon=False):
            self._target = target

        def start(self):
            self._target()  # run synchronously so the test can assert on it

    with patch("quodeq.update.checker.threading.Thread", _SyncThread), \
         patch("quodeq.update.checker.fetch_latest", side_effect=RuntimeError("boom")), \
         caplog.at_level(logging.WARNING, logger="quodeq.update.checker"):
        checker.check_async(env)  # must not raise

    assert "update check failed" in caplog.text
    # Review fix -- the attempt timestamp is now persisted BEFORE the network
    # call, so it's there even though run_isolated caught the failure above.
    assert read_state(env).last_check_ts is not None


def test_check_async_logs_a_warning_on_thread_start_failure(tmp_path, caplog) -> None:
    """R-FT-7 -- Thread.start()'s only documented failure (RuntimeError) is
    now logged at warning, not swallowed at debug."""
    env = _env(tmp_path)

    class _FailingThread:
        def __init__(self, target, daemon=False):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")

    with patch("quodeq.update.checker.threading.Thread", _FailingThread), \
         caplog.at_level(logging.WARNING, logger="quodeq.update.checker"):
        checker.check_async(env)  # must not raise

    assert "could not start update-check thread" in caplog.text
