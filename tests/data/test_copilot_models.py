import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from quodeq.data.copilot_models import fetch_copilot_models


@pytest.fixture
def cli(tmp_path, monkeypatch):
    original = asyncio.create_subprocess_exec
    calls = []
    script = tmp_path / "fake_cli.py"

    def configure(response, *, delay=0, header=None, ignore_terminate=False):
        body = json.dumps(response).encode()
        frame = header if header is not None else f"Content-Length: {len(body)}\r\n\r\n".encode() + body
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
    frames = b""
    for response in [{"jsonrpc": "2.0", "method": "status"}, result([{"id": "gpt-test"}])]:
        body = json.dumps(response).encode()
        frames += f"Content-Length: {len(body)}\r\n\r\n".encode() + body
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
