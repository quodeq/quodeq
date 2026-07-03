from quodeq.assistant.adapters._capabilities import supports_native_tools


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
