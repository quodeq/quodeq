"""API routes for LLM bridge — provider status, models, testing."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.config.ai_provider import store_api_key, get_api_key_secure
from quodeq.llm_bridge import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    run_concurrency_test,
    get_llamacpp_status,
    list_llamacpp_models,
    run_llamacpp_concurrency_test,
    get_omlx_status,
    list_omlx_models,
    run_omlx_concurrency_test,
    get_known_models,
    get_provider_configs,
    check_cloud_connection,
    resolve_api_key,
)
from quodeq.shared.url_validation import url_safety_error

from quodeq.api._llm_bridge_validation import (
    BODY_NOT_OBJECT,
    invalid_base_url,
    json_body,
    require_model_name,
    string_fields_error,
)


def ollama_status() -> Response:
    """Report whether a local Ollama daemon is reachable and what it is serving."""
    return jsonify(get_ollama_status())


def ollama_models() -> Response:
    """List the models the local Ollama daemon has pulled, for the model picker."""
    return jsonify({"models": list_ollama_models()})


def ollama_test_concurrency() -> Response:
    """Probe how many subagents the local Ollama can serve in parallel for a model.

    Runs real inference, so it is slow; the settings UI calls it once when the
    user asks to measure rather than on every render.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    model, err = require_model_name(data, require_nonempty=True)
    if err is not None:
        return err
    result = run_concurrency_test(model)
    return jsonify(result)


def ollama_estimate_agents() -> Response:
    """Estimate a safe subagent count from model size and GPU memory.

    The cheap alternative to ``ollama_test_concurrency``: arithmetic only, no
    inference, so the settings UI can suggest a number while the user types.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    model_size = data.get("model_size", 0)
    gpu_memory = data.get("gpu_memory", 0)
    if (isinstance(model_size, bool) or isinstance(gpu_memory, bool)
            or not isinstance(model_size, (int, float))
            or not isinstance(gpu_memory, (int, float))):
        return jsonify({"error": "model_size and gpu_memory must be numbers", "code": "INVALID_PARAM"}), 400
    return jsonify(estimate_max_agents(model_size=model_size, gpu_memory=gpu_memory))


def llamacpp_status() -> Response:
    """Report whether a local llama.cpp server is reachable and what it is serving."""
    return jsonify(get_llamacpp_status())


def llamacpp_models() -> Response:
    """List the models the local llama.cpp server exposes, for the model picker."""
    return jsonify({"models": list_llamacpp_models()})


def llamacpp_test_concurrency() -> Response:
    """Probe how many subagents the local llama.cpp server can serve in parallel.

    Unlike the ollama route, an empty ``model`` is accepted: llama.cpp serves
    whatever it was started with.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    model, err = require_model_name(data, require_nonempty=False)
    if err is not None:
        return err
    result = run_llamacpp_concurrency_test(model)
    return jsonify(result)


def omlx_status() -> Response:
    """Report whether the omlx server at ``?base_url=`` is reachable.

    The base URL is a request parameter rather than config because omlx is
    typically self-hosted somewhere on the LAN and the user is still typing
    the address into settings when this is called.
    """
    base_url = request.args.get("base_url", "").strip() or None
    err = invalid_base_url(base_url)
    if err is not None:
        return err
    return jsonify(get_omlx_status(base_url=base_url))


def omlx_models() -> Response:
    """List the models the omlx server at ``?base_url=`` exposes.

    The API key rides in the ``X-Api-Key`` header, never the query string.
    """
    base_url = request.args.get("base_url", "").strip() or None
    err = invalid_base_url(base_url)
    if err is not None:
        return err
    # The key rides in a header, never the query string: query params leak
    # through access logs, browser history, and referrers.
    api_key = (request.headers.get("X-Api-Key") or "").strip() or None
    return jsonify({"models": list_omlx_models(base_url=base_url, api_key=api_key)})


def omlx_test_concurrency() -> Response:
    """Probe how many subagents the omlx server can serve in parallel.

    Takes the server address and key in the body rather than from config, so
    the user can measure a server before saving it.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    model, err = require_model_name(data, require_nonempty=False)
    if err is not None:
        return err
    base_url = data.get("base_url") or ""
    api_key = data.get("api_key") or ""
    if not isinstance(base_url, str) or not isinstance(api_key, str):
        return jsonify({"error": "base_url and api_key must be strings", "code": "INVALID_PARAM"}), 400
    base_url = base_url.strip() or None
    api_key = api_key.strip() or None
    err = invalid_base_url(base_url)
    if err is not None:
        return err
    result = run_omlx_concurrency_test(model, base_url=base_url, api_key=api_key)
    return jsonify(result)


def provider_test() -> Response:
    """Try one round-trip against a cloud provider and report the outcome.

    The settings UI calls this before saving so a wrong base URL, model name
    or missing key surfaces there instead of mid-evaluation. When the body
    carries no key, the provider's env var is resolved by provider id, or by
    api_base match for clients predating the ``provider`` field.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    if (err := string_fields_error(data, ("provider", "api_base", "api_key", "model"))):
        return err
    configs = get_provider_configs()
    provider_id = data.get("provider", "")
    provider_cfg = configs.get(provider_id, {}) if provider_id else {}

    api_base = data.get("api_base") or provider_cfg.get("api_base", "")
    api_key = data.get("api_key", "")
    api_key_env = ""
    if not api_key:
        # Resolve env var via provider id when given, else by api_base
        # match so old clients (without `provider`) still work.
        api_key, api_key_env = resolve_api_key(provider_id, api_base)

    if api_base:
        err = url_safety_error(api_base, allow_private=True)
        if err is not None:
            return jsonify({"error": err, "code": "INVALID_URL"}), 400
    if not api_key and api_key_env:
        return jsonify({
            "success": False,
            "code": "MISSING_API_KEY",
            "error": f"{api_key_env} is not set in the dashboard's environment. "
                     f"Export it in your shell (e.g. ~/.zshrc) and relaunch the dashboard from that terminal.",
        })
    result = check_cloud_connection(
        api_base=api_base,
        model=data.get("model", ""),
        api_key=api_key,
    )
    return jsonify(result)


def provider_env_check() -> Response:
    """Report which provider api-key env vars are visible to this process."""
    configs = get_provider_configs()
    seen: dict[str, bool] = {}
    for pid in configs:
        key, env_name = resolve_api_key(pid)
        if env_name:
            seen[pid] = bool(key.strip())
    return jsonify(seen)


def provider_store_key() -> Response:
    """Persist a provider API key, preferring the OS keychain.

    Returns ``{"stored", "secure"}``; ``secure`` is False when the keychain
    was unavailable and the key fell back to ``.quodeq.env`` on disk, which
    the UI surfaces as a warning.
    """
    data = json_body()
    if data is None:
        return jsonify(BODY_NOT_OBJECT), 400
    provider = data.get("provider", "")
    api_key = data.get("apiKey", "")
    if not provider or not isinstance(provider, str):
        return jsonify({"error": "provider is required", "code": "MISSING_PARAM"}), 400
    if not api_key or not isinstance(api_key, str):
        return jsonify({"error": "apiKey is required", "code": "MISSING_PARAM"}), 400
    try:
        stored, secure = store_api_key(provider, api_key)
    except ValueError:
        # Provider names are interpolated into `.quodeq.env` lines, so a
        # name with control characters is rejected outright rather than
        # being allowed to inject extra `export …` lines.
        #
        # A fixed message, not str(exc): echoing exception text back to a
        # client is the shape of an information-disclosure bug even when
        # every reachable message here happens to be a constant today,
        # and CodeQL flags it as one. Nothing is lost -- the only
        # ValueError that reaches this handler already says exactly this.
        return jsonify({
            "error": "Provider name must contain only letters, digits, '-' and '_'",
            "code": "INVALID_PARAM",
        }), 400
    return jsonify({"stored": stored, "secure": secure})


def provider_key_status() -> Response:
    """Report whether a key for ``?provider=`` is in the keychain.

    Only the boolean crosses the wire; the key itself never leaves the
    server, so the UI can show "configured" without being able to read it.
    """
    provider = request.args.get("provider", "")
    if not provider:
        return jsonify({"error": "provider is required", "code": "MISSING_PARAM"}), 400
    return jsonify({"configured": get_api_key_secure(provider) is not None})


def known_models() -> Response:
    """Return the curated model catalogue the settings model picker offers."""
    return jsonify(get_known_models())


def provider_configs() -> Response:
    """Return each supported cloud provider's default base URL and key env var."""
    return jsonify(get_provider_configs())


def register_llm_bridge_routes(app: Flask) -> None:
    """Bind the llm_bridge API routes to their module-level handlers."""
    app.get("/api/ollama/status")(ollama_status)
    app.get("/api/ollama/models")(ollama_models)
    app.post("/api/ollama/test-concurrency")(ollama_test_concurrency)
    app.post("/api/ollama/estimate-agents")(ollama_estimate_agents)
    app.get("/api/llamacpp/status")(llamacpp_status)
    app.get("/api/llamacpp/models")(llamacpp_models)
    app.post("/api/llamacpp/test-concurrency")(llamacpp_test_concurrency)
    app.get("/api/omlx/status")(omlx_status)
    app.get("/api/omlx/models")(omlx_models)
    app.post("/api/omlx/test-concurrency")(omlx_test_concurrency)
    app.post("/api/provider/test")(provider_test)
    app.get("/api/provider/env-check")(provider_env_check)
    app.post("/api/provider/key")(provider_store_key)
    app.get("/api/provider/key-status")(provider_key_status)
    app.get("/api/known-models")(known_models)
    app.get("/api/provider-configs")(provider_configs)
