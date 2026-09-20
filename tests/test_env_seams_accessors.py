"""Each environment read takes an explicit mapping; ``os.environ`` is only the default."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clear_process_env(monkeypatch):
    for name in (
        "QUODEQ_CONTEXT_SIZE", "QUODEQ_CACHE_ROOT", "QUODEQ_LOG_STREAM_POLL_MS",
        "QUODEQ_LOG_STREAM_MAX_WAIT_S", "QUODEQ_NPM_INSTALL_TIMEOUT_S",
        "QUODEQ_NPM_BUILD_TIMEOUT_S", "LLAMACPP_BASE_URL", "QUODEQ_JOB_PERSIST_DIR",
        "QUODEQ_AI_PROVIDERS_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_extra_body_reads_context_size_from_injected_env():
    from quodeq.assistant.adapters._api import ApiTurnConfig, _extra_body

    config = ApiTurnConfig(api_base="http://localhost:11434/v1", api_key=None,
                           model="m", native_tools=False)
    assert "num_ctx" not in _extra_body(config)
    assert _extra_body(config, env={"QUODEQ_CONTEXT_SIZE": "4096"})["num_ctx"] == 4096


def test_default_cache_root_honours_injected_env(tmp_path: Path):
    from quodeq.data.cache_store.local import default_cache_root

    assert default_cache_root(env={"QUODEQ_CACHE_ROOT": str(tmp_path)}) == tmp_path / "results"
    assert default_cache_root(env={}) == Path.home() / ".quodeq" / "cache" / "results"


def test_sse_poll_and_wait_tuning_honour_injected_env():
    from quodeq.api._sse_log_helpers import _max_wait_s, _poll_ms

    assert _poll_ms() == 100
    assert _max_wait_s() == 10
    assert _poll_ms(env={"QUODEQ_LOG_STREAM_POLL_MS": "5"}) == 5
    assert _max_wait_s(env={"QUODEQ_LOG_STREAM_MAX_WAIT_S": "1"}) == 1


def test_npm_timeouts_honour_injected_env():
    from quodeq.dashboard._build_npm import _npm_build_timeout_s, _npm_install_timeout_s

    assert _npm_install_timeout_s() == 300
    assert _npm_build_timeout_s() == 600
    assert _npm_install_timeout_s(env={"QUODEQ_NPM_INSTALL_TIMEOUT_S": "7"}) == 7
    assert _npm_build_timeout_s(env={"QUODEQ_NPM_BUILD_TIMEOUT_S": "9"}) == 9


def test_llamacpp_base_url_is_read_at_call_time(monkeypatch):
    from quodeq.llm_bridge import _llamacpp

    assert _llamacpp._default_base_url() == "http://localhost:8080"
    assert _llamacpp._default_base_url(env={"LLAMACPP_BASE_URL": "http://x:1"}) == "http://x:1"
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://late:2")
    seen: list[str] = []
    monkeypatch.setattr(_llamacpp, "_normalize_base", lambda url: seen.append(url) or "http://late:2")
    monkeypatch.setattr(_llamacpp.urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    _llamacpp.get_llamacpp_status()
    assert seen == ["http://late:2"]


def test_default_persist_dir_honours_injected_env(tmp_path: Path):
    from quodeq.services._job_file_store import _default_persist_dir

    assert _default_persist_dir(env={"QUODEQ_JOB_PERSIST_DIR": str(tmp_path)}) == tmp_path


def test_providers_path_honours_injected_env(tmp_path: Path):
    from quodeq.shared.provider_env import _DEFAULT_PATH, providers_path

    assert providers_path(env={}) == _DEFAULT_PATH
    assert providers_path(env={"QUODEQ_AI_PROVIDERS_PATH": str(tmp_path / "p.json")}) == tmp_path / "p.json"
