from pathlib import Path

from quodeq.dashboard import _api_spawn, runner
from quodeq.dashboard._api_health import ApiConfig
from quodeq.dashboard._api_spawn import spawn_action_api
from quodeq.dashboard._probes import DashboardHooks

from tests.conftest import DummyProcess
import pytest

# The code under test sets PYTHONUTF8 / QUODEQ_WEBVIEW_TOKEN for the process;
# restore os.environ wholesale so the env-leak guard in tests/conftest.py stays green.
pytestmark = pytest.mark.usefixtures("restore_environ")

_TEST_PORT = 7863
_TEST_HOST = "127.0.0.1"
_TEST_DASHBOARD_PORT = 3000
_TEST_API_PORT = 9000


def test_spawn_action_api_sets_env(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env
        return DummyProcess()

    monkeypatch.setattr(_api_spawn.subprocess, "Popen", fake_popen)
    spawn_action_api(_TEST_PORT, tmp_path / "fake.pid", _TEST_HOST)
    assert captured["env"]["QUODEQ_ACTION_API_PORT"] == str(_TEST_PORT)


def test_spawn_action_api_sets_static_dist(monkeypatch, tmp_path):
    captured = {}

    def fake_popen(cmd, env=None, **kwargs):
        captured["env"] = env
        return DummyProcess()

    dist_path = tmp_path / "dist"
    monkeypatch.setattr(_api_spawn.subprocess, "Popen", fake_popen)
    spawn_action_api(_TEST_PORT, tmp_path / "fake.pid", _TEST_HOST, ApiConfig(static_dist=dist_path))
    assert captured["env"]["QUODEQ_STATIC_DIST"] == str(dist_path)


def test_force_action_api_host_port(monkeypatch):
    captured = {}

    class FakeProcess:
        def poll(self):
            return 0  # already exited

        def wait(self, timeout=None):
            return 0

        def terminate(self):
            pass

    def fake_ensure(host, port, static_dist=None, evaluations_dir=None, **_kwargs):
        captured["host"] = host
        captured["port"] = port
        return f"http://{host}:{port}", FakeProcess()

    monkeypatch.setattr(runner, "ensure_action_api_forced", fake_ensure)
    monkeypatch.setattr(runner, "validate_paths", lambda *_args, **_kwargs: None)
    hooks = DashboardHooks(
        build_ui=lambda *_args, **_kwargs: Path("ui/web/dist"),
        check_prereqs=lambda: None,
    )

    config = runner.DashboardConfig(
        server=runner.ServerConfig(
            port=_TEST_DASHBOARD_PORT,
            api_host="0.0.0.0",
            api_port=_TEST_API_PORT,
            api_forced=True,
        ),
        build=runner.BuildConfig(
            open_browser=False,
            no_build=True,
            reinstall=False,
        ),
        reports_dir=Path("reports"),
        static_dist=Path("ui/web/dist"),
        repo_root=Path("."),
        reports_defaulted=True,
    )

    runner.run_dashboard(config, hooks=hooks)
    assert captured == {"host": "0.0.0.0", "port": 9000}


class _StubbornProcess:
    """A live process whose post-SIGTERM wait can time out."""

    def __init__(self, ignores_sigterm: bool):
        self.ignores_sigterm = ignores_sigterm
        self.calls: list[tuple[str, float | None]] = []

    def poll(self):
        return None

    def terminate(self):
        self.calls.append(("terminate", None))

    def kill(self):
        self.calls.append(("kill", None))

    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        if timeout is not None and self.ignores_sigterm:
            raise _api_spawn.subprocess.TimeoutExpired("api", timeout)
        return 0


def _spawn_failing_health(monkeypatch, tmp_path, proc):
    def unhealthy(_base_url):
        raise TimeoutError("not healthy")

    monkeypatch.setattr(_api_spawn, "spawn_action_api", lambda *_a, **_k: proc)
    monkeypatch.setattr(_api_spawn, "wait_for_action_api", unhealthy)
    with pytest.raises(TimeoutError):
        _api_spawn.spawn_and_wait(_TEST_PORT, "http://x", tmp_path / "p.pid", _TEST_HOST)


def test_spawn_and_wait_bounds_the_wait_after_sigterm(monkeypatch, tmp_path):
    proc = _StubbornProcess(ignores_sigterm=False)
    _spawn_failing_health(monkeypatch, tmp_path, proc)
    assert proc.calls == [("terminate", None), ("wait", _api_spawn.TERMINATE_GRACE_SECONDS)]


def test_spawn_and_wait_kills_a_child_that_ignores_sigterm(monkeypatch, tmp_path):
    proc = _StubbornProcess(ignores_sigterm=True)
    _spawn_failing_health(monkeypatch, tmp_path, proc)
    assert proc.calls == [
        ("terminate", None),
        ("wait", _api_spawn.TERMINATE_GRACE_SECONDS),
        ("kill", None),
        ("wait", None),
    ]
