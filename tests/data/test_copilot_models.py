import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from quodeq.data.copilot_models import fetch_copilot_models


def _frame(response: dict) -> bytes:
    """One JSON-RPC message as the CLI writes it: Content-Length header, then body."""
    body = json.dumps(response).encode()
    return f"Content-Length: {len(body)}\r\n\r\n".encode() + body


@pytest.fixture
def cli(tmp_path, monkeypatch):
    original = asyncio.create_subprocess_exec
    calls = []
    script = tmp_path / "fake_cli.py"

    def configure(response, *, delay=0, header=None, ignore_terminate=False):
        frame = header if header is not None else _frame(response)
        signal_setup = "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n" if ignore_terminate else ""
        script.write_text(
            "import sys,time,json,signal\n"
            f"{signal_setup}"
            "header=sys.stdin.buffer.readline()\n"
            "sys.stdin.buffer.readline()\n"
            "request=json.loads(sys.stdin.buffer.read(int(header.split(b':')[1])))\n"
            "assert request['method']=='models.list'\n"
            "assert request['params']=={}\n"
            f"time.sleep({delay})\n"
            f"sys.stdout.buffer.write({frame!r})\n"
            "sys.stdout.buffer.flush()\n"
            "sys.stdin.buffer.read()\n"
        )

    async def launch(*args, **kwargs):
        process = await original(sys.executable, str(script), **kwargs)
        calls.append((args, kwargs, process))
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    return configure, calls, {"HOME": str(tmp_path), "PATH": "/bin", "GITHUB_TOKEN": "not-inherited"}


def result(models):
    return {"jsonrpc": "2.0", "id": "quodeq-models", "result": {"models": models}}


def test_discovers_account_models_without_inference_and_cleans_up(cli):
    configure, calls, env = cli
    configure(result([
        {"id": "gpt-test"},
        {"id": "claude-test", "policy": {"state": "enabled"}},
        {"id": "blocked-test", "policy": {"state": "disabled"}},
        {"id": "gpt-test"},
    ]))
    assert fetch_copilot_models(env=env) == {"models": ["auto", "gpt-test", "claude-test"]}
    args, kwargs, process = calls[0]
    assert "--headless" in args and "--stdio" in args
    assert "--disable-builtin-mcps" in args and "--no-custom-instructions" in args
    assert "-p" not in args
    assert Path(kwargs["env"]["COPILOT_HOME"]) == Path(env["HOME"]) / ".quodeq" / "copilot"
    assert "GITHUB_TOKEN" not in kwargs["env"]
    assert not kwargs["cwd"].exists()
    assert process.returncode is not None


@pytest.mark.parametrize("response", [
    result(None), result([None]), result([{"id": 123}]), result([]),
    result([{"id": "gpt-test", "policy": "invalid"}]),
    {"jsonrpc": "2.0", "id": "quodeq-models", "error": []},
    result([{"id": "blocked", "policy": {"state": "disabled"}}]),
    {"jsonrpc": "2.0", "id": "quodeq-models", "error": {"message": "Authentication required"}},
])
def test_discovery_failure_is_explicit_and_logged(cli, response, caplog):
    configure, calls, env = cli
    configure(response)
    payload = fetch_copilot_models(env=env)
    assert payload["models"] == []
    assert payload["error"]
    assert payload["error_code"] == "COPILOT_MODELS_UNAVAILABLE"
    assert "Copilot model discovery failed" in caplog.text
    assert calls[0][2].returncode is not None


def test_timeout_terminates_the_process(cli):
    configure, calls, env = cli
    configure(result([{"id": "gpt-test"}]), delay=10)
    payload = fetch_copilot_models(env=env, timeout_s=0.1)
    assert "timed out" in payload["error"].lower()
    assert calls[0][2].returncode is not None


@pytest.mark.parametrize("header", [
    b"Content-Length: -1\r\n\r\n", b"Content-Length: 999999999\r\n\r\n",
    b"Invalid: 0\r\n\r\n", b"Content-Length: 1\r\n\r\n{", b"Content-Length: 4\r\n\r\nnull",
])
def test_rejects_invalid_rpc_frames(cli, header):
    configure, _, env = cli
    configure({}, header=header)
    payload = fetch_copilot_models(env=env)
    assert payload["error_code"] == "COPILOT_MODELS_UNAVAILABLE"


def test_ignores_notifications_before_the_model_response(cli):
    configure, _, env = cli
    frames = b"".join(
        _frame(response)
        for response in [{"jsonrpc": "2.0", "method": "status"}, result([{"id": "gpt-test"}])]
    )
    configure({}, header=frames)
    assert fetch_copilot_models(env=env)["models"] == ["auto", "gpt-test"]


def test_missing_cli_is_an_explicit_failure(tmp_path, monkeypatch):
    async def missing(*args, **kwargs):
        raise FileNotFoundError("copilot executable not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing)
    payload = fetch_copilot_models(env={"HOME": str(tmp_path)})
    assert payload["error_code"] == "COPILOT_MODELS_UNAVAILABLE"


def test_local_exception_details_are_logged_not_exposed(tmp_path, monkeypatch, caplog):
    async def missing(*args, **kwargs):
        raise OSError("private/internal/path")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", missing)
    payload = fetch_copilot_models(env={"HOME": str(tmp_path)})
    assert "private/internal/path" not in payload["error"]
    assert "private/internal/path" in caplog.text


def test_rpc_error_secrets_are_redacted(cli, caplog):
    configure, _, env = cli
    secret = "ghp_" + "a" * 36
    configure({"id": "quodeq-models", "error": {"message": f"Authentication failed: {secret}"}})
    payload = fetch_copilot_models(env=env)
    assert secret not in payload["error"]
    assert secret not in caplog.text


@pytest.mark.skipif(os.name == "nt", reason="POSIX termination signals")
def test_forces_cleanup_if_cli_ignores_termination(cli, monkeypatch):
    configure, calls, env = cli
    configure(result([{"id": "gpt-test"}]), ignore_terminate=True)
    monkeypatch.setattr("quodeq.data.copilot_models._STOP_TIMEOUT_S", 0.01)
    assert fetch_copilot_models(env=env)["models"] == ["auto", "gpt-test"]
    assert calls[0][2].returncode is not None


def test_cleanup_handle_race_does_not_discard_the_models(cli, monkeypatch):
    """Windows regression (flaked on PR #1220 CI): the just-terminated CLI can
    hold a handle on its cwd for a moment, so the first rmtree fails with
    WinError 32. That exception used to fire after the model list already
    existed and turned a successful discovery into COPILOT_MODELS_UNAVAILABLE.
    Cleanup must retry past the transient failure and still remove the dir."""

    configure, calls, env = cli
    configure(result([{"id": "gpt-test"}]))
    real_rmtree = shutil.rmtree
    attempts = []

    def rmtree_busy_once(path, *args, **kwargs):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError(
                "[WinError 32] The process cannot access the file because "
                "it is being used by another process",
            )
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", rmtree_busy_once)
    assert fetch_copilot_models(env=env) == {"models": ["auto", "gpt-test"]}
    assert len(attempts) == 2
    assert not calls[0][1]["cwd"].exists()


def test_process_factory_seam_avoids_monkeypatching_asyncio(tmp_path):
    """fetch_copilot_models accepts a process_factory instead of requiring
    asyncio.create_subprocess_exec itself to be monkeypatched."""
    body = json.dumps(result([{"id": "gpt-test"}])).encode()
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode() + body
    script = tmp_path / "fake_cli.py"
    script.write_text(
        "import sys,json\n"
        "header=sys.stdin.buffer.readline()\n"
        "sys.stdin.buffer.readline()\n"
        "sys.stdin.buffer.read(int(header.split(b':')[1]))\n"
        f"sys.stdout.buffer.write({frame!r})\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stdin.buffer.read()\n"
    )

    async def factory(*args, **kwargs):
        return await asyncio.create_subprocess_exec(sys.executable, str(script), **kwargs)

    env = {"HOME": str(tmp_path), "PATH": "/bin"}
    payload = fetch_copilot_models(env=env, process_factory=factory)
    assert payload == {"models": ["auto", "gpt-test"]}


def test_cleanup_never_outranks_the_result_even_when_it_keeps_failing(cli, monkeypatch):
    """If the handle outlives every retry, the scratch dir is left to the OS
    temp cleaner; the discovery result must still come through untouched."""

    configure, calls, env = cli
    configure(result([{"id": "gpt-test"}]))
    monkeypatch.setattr(
        "quodeq.data.copilot_models._CLEANUP_RETRY_DELAY_S", 0.001,
    )

    def rmtree_always_busy(path, *args, **kwargs):
        raise OSError("[WinError 32] busy")

    monkeypatch.setattr(shutil, "rmtree", rmtree_always_busy)
    assert fetch_copilot_models(env=env) == {"models": ["auto", "gpt-test"]}
    assert calls[0][1]["cwd"].exists()
