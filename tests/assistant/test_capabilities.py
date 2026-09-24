from quodeq.assistant.adapters.capabilities import supports_native_tools


def test_cloud_providers_assumed_native():
    assert supports_native_tools("openrouter", "https://openrouter.ai/api/v1", "m")
    assert supports_native_tools("custom", "https://x/v1", "m")


def test_local_default_false():
    assert not supports_native_tools("llamacpp", "http://localhost:8080/v1", "m")
    assert not supports_native_tools("omlx", "http://localhost:10240/v1", "m")


def test_ollama_show_probe_positive_and_negative():
    def probe_yes(url, json):
        assert url == "http://localhost:11434/api/show"
        assert json == {"model": "qwen3"}
        return {"capabilities": ["completion", "tools"]}

    def probe_no(url, json):
        return {"capabilities": ["completion"]}

    assert supports_native_tools("ollama", "http://localhost:11434/v1", "qwen3", probe=probe_yes)
    assert not supports_native_tools("ollama", "http://localhost:11434/v1", "qwen3", probe=probe_no)


def test_ollama_probe_error_means_false():
    def probe_boom(url, json):
        raise OSError("connection refused")

    assert not supports_native_tools("ollama", "http://localhost:11434/v1", "m", probe=probe_boom)


def _counting_default_probe(monkeypatch, answer):
    calls: list[str] = []

    def probe(url, json):
        calls.append(url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr("quodeq.assistant.adapters.capabilities._default_probe", probe)
    return calls


def test_a_successful_probe_is_asked_once_per_model(monkeypatch):
    calls = _counting_default_probe(monkeypatch, {"capabilities": ["tools"]})
    base = "http://cache-hit-host:11434/v1"
    assert supports_native_tools("ollama", base, "qwen3")
    assert supports_native_tools("ollama", base, "qwen3")
    assert supports_native_tools("ollama", base, "other-model")
    assert len(calls) == 2


def test_a_failed_probe_is_asked_again(monkeypatch):
    calls = _counting_default_probe(monkeypatch, OSError("connection refused"))
    base = "http://cache-miss-host:11434/v1"
    assert not supports_native_tools("ollama", base, "qwen3")
    assert not supports_native_tools("ollama", base, "qwen3")
    assert len(calls) == 2


def test_an_injected_probe_is_never_cached():
    calls: list[str] = []

    def probe(url, json):
        calls.append(url)
        return {"capabilities": ["tools"]}

    base = "http://injected-host:11434/v1"
    supports_native_tools("ollama", base, "qwen3", probe=probe)
    supports_native_tools("ollama", base, "qwen3", probe=probe)
    assert len(calls) == 2
