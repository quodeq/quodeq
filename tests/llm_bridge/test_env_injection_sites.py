"""llm_bridge seams resolve their env through the config layer, at call time.

The base URLs used to be module constants captured at import, so a variable
exported after the first import was ignored for the rest of the process.
They are read per call now; these tests pin that.
"""
from __future__ import annotations

from quodeq.llm_bridge import _llamacpp, _ollama, _omlx, _providers


def test_llamacpp_base_url_honours_injected_env(monkeypatch):
    monkeypatch.setenv("LLAMACPP_BASE_URL", "http://from-process:1")
    assert _llamacpp._default_base_url(env={"LLAMACPP_BASE_URL": "http://x:2"}) == "http://x:2"
    assert _llamacpp._default_base_url(env={}) == "http://localhost:8080"


def test_ollama_base_url_is_read_per_call(monkeypatch):
    assert _ollama._resolved_base(None) == "http://localhost:11434"
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:9991")
    assert _ollama._resolved_base(None) == "http://localhost:9991"
    assert _ollama._resolved_base("http://explicit:1") == "http://explicit:1"


def test_ollama_status_probes_the_late_bound_base(monkeypatch):
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):
        seen.append(req.full_url)
        raise OSError("no server")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:9991")
    _ollama.get_ollama_status()
    assert seen == ["http://localhost:9991/api/version"]


def test_omlx_base_url_is_read_per_call(monkeypatch):
    seen: list[str] = []

    def fake_urlopen(req, timeout=None):
        seen.append(req.full_url)
        raise OSError("no server")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("OMLX_BASE_URL", "http://localhost:9992")
    _omlx.get_omlx_status()
    assert seen == ["http://localhost:9992/health"]


def test_omlx_api_key_honours_injected_env(monkeypatch):
    monkeypatch.setenv("OMLX_API_KEY", "from-process")
    assert _omlx.read_omlx_api_key(env={"OMLX_API_KEY": "sk-injected"}) == "sk-injected"
    # env={} means "nothing set": the process value must not leak in. The
    # settings.json fallback is the only remaining source.
    monkeypatch.setattr(
        "quodeq.llm_bridge._omlx.Path.home", lambda: __import__("pathlib").Path("/nonexistent"))
    assert _omlx.read_omlx_api_key(env={}) == ""


def test_local_api_markers_honours_injected_env(monkeypatch):
    monkeypatch.setenv("QUODEQ_LOCAL_API_MARKERS", "from-process")
    assert _providers._local_api_markers(
        env={"QUODEQ_LOCAL_API_MARKERS": "a,b"}) == frozenset({"a", "b"})
    assert _providers._local_api_markers(env={}) == frozenset(
        {"11434", "localhost", "127.0.0.1", "ollama"})


def test_resolve_api_key_honours_injected_env(monkeypatch):
    monkeypatch.setenv("FAKE_KEY", "from-process")
    monkeypatch.setattr(
        _providers, "get_provider_configs",
        lambda: {"fake": {"type": "api", "api_key_env": "FAKE_KEY"}})
    assert _providers.resolve_api_key("fake", env={"FAKE_KEY": "sk-1"}) == ("sk-1", "FAKE_KEY")
    assert _providers.resolve_api_key("fake", env={}) == ("", "FAKE_KEY")
