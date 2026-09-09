"""API routes for LLM bridge — provider status, models, testing."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.config.ai_provider import _store_api_key, get_api_key_secure
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
from quodeq.shared.url_validation import validate_url_safe


def _json_body() -> dict | None:
    """Return the request's JSON body when it is an object, else None.

    A body like ``[1]`` or ``"x"`` parses as valid JSON but crashes the
    ``data.get(...)`` calls below with an AttributeError (a 500); callers
    turn None into a 400 instead.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


_BODY_NOT_OBJECT = {"error": "request body must be a JSON object", "code": "INVALID_PARAM"}


def _invalid_base_url(base_url: str | None) -> tuple[Response, int] | None:
    """Return a 400 response when *base_url* fails SSRF validation, else None.

    Same policy as /api/provider/test: http(s) scheme only, private/LAN
    addresses allowed (self-hosted omlx servers are the normal case).
    """
    if base_url is None:
        return None
    try:
        validate_url_safe(base_url, allow_private=True)
    except ValueError as exc:
        return jsonify({"error": str(exc), "code": "INVALID_URL"}), 400
    return None


def _invalid_model_name(model: str) -> tuple[Response, int] | None:
    """Return a 400 response when *model* contains invalid characters, else None.

    Prevents path traversal and null-byte injection.
    """
    if "\\" in model or ".." in model or "\0" in model:
        return jsonify({"error": "Invalid model name", "code": "INVALID_PARAM"}), 400
    return None


def _require_model_name(
    data: dict, *, require_nonempty: bool,
) -> tuple[str | None, tuple[Response, int] | None]:
    """Validate the ``model`` field shared by the concurrency-test routes.

    ollama requires a non-empty string (``require_nonempty=True``, rejects
    ``""`` with MISSING_PARAM); llamacpp and omlx accept an empty string and
    only reject non-strings (``require_nonempty=False``, INVALID_PARAM).
    """
    model = data.get("model", "")
    if require_nonempty:
        if not model or not isinstance(model, str):
            return None, (jsonify({"error": "model is required", "code": "MISSING_PARAM"}), 400)
    elif not isinstance(model, str):
        return None, (jsonify({"error": "model must be a string", "code": "INVALID_PARAM"}), 400)
    err = _invalid_model_name(model)
    if err is not None:
        return None, err
    return model, None


def register_llm_bridge_routes(app: Flask) -> None:
    """Register all llm_bridge API routes."""

    @app.get("/api/ollama/status")
    def ollama_status() -> Response:
        return jsonify(get_ollama_status())

    @app.get("/api/ollama/models")
    def ollama_models() -> Response:
        return jsonify({"models": list_ollama_models()})

    @app.post("/api/ollama/test-concurrency")
    def ollama_test_concurrency() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
        model, err = _require_model_name(data, require_nonempty=True)
        if err is not None:
            return err
        result = run_concurrency_test(model)
        return jsonify(result)

    @app.post("/api/ollama/estimate-agents")
    def ollama_estimate_agents() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
        model_size = data.get("model_size", 0)
        gpu_memory = data.get("gpu_memory", 0)
        if (isinstance(model_size, bool) or isinstance(gpu_memory, bool)
                or not isinstance(model_size, (int, float))
                or not isinstance(gpu_memory, (int, float))):
            return jsonify({"error": "model_size and gpu_memory must be numbers", "code": "INVALID_PARAM"}), 400
        return jsonify(estimate_max_agents(model_size=model_size, gpu_memory=gpu_memory))

    @app.get("/api/llamacpp/status")
    def llamacpp_status() -> Response:
        return jsonify(get_llamacpp_status())

    @app.get("/api/llamacpp/models")
    def llamacpp_models() -> Response:
        return jsonify({"models": list_llamacpp_models()})

    @app.post("/api/llamacpp/test-concurrency")
    def llamacpp_test_concurrency() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
        model, err = _require_model_name(data, require_nonempty=False)
        if err is not None:
            return err
        result = run_llamacpp_concurrency_test(model)
        return jsonify(result)

    @app.get("/api/omlx/status")
    def omlx_status() -> Response:
        base_url = request.args.get("base_url", "").strip() or None
        err = _invalid_base_url(base_url)
        if err is not None:
            return err
        return jsonify(get_omlx_status(base_url=base_url))

    @app.get("/api/omlx/models")
    def omlx_models() -> Response:
        base_url = request.args.get("base_url", "").strip() or None
        err = _invalid_base_url(base_url)
        if err is not None:
            return err
        # The key rides in a header, never the query string: query params leak
        # through access logs, browser history, and referrers.
        api_key = (request.headers.get("X-Api-Key") or "").strip() or None
        return jsonify({"models": list_omlx_models(base_url=base_url, api_key=api_key)})

    @app.post("/api/omlx/test-concurrency")
    def omlx_test_concurrency() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
        model, err = _require_model_name(data, require_nonempty=False)
        if err is not None:
            return err
        base_url = data.get("base_url") or ""
        api_key = data.get("api_key") or ""
        if not isinstance(base_url, str) or not isinstance(api_key, str):
            return jsonify({"error": "base_url and api_key must be strings", "code": "INVALID_PARAM"}), 400
        base_url = base_url.strip() or None
        api_key = api_key.strip() or None
        err = _invalid_base_url(base_url)
        if err is not None:
            return err
        result = run_omlx_concurrency_test(model, base_url=base_url, api_key=api_key)
        return jsonify(result)

    @app.post("/api/provider/test")
    def provider_test() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
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
            try:
                validate_url_safe(api_base, allow_private=True)
            except ValueError as exc:
                return jsonify({"error": str(exc), "code": "INVALID_URL"}), 400
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

    @app.get("/api/provider/env-check")
    def provider_env_check() -> Response:
        """Report which provider api-key env vars are visible to this process."""
        configs = get_provider_configs()
        seen: dict[str, bool] = {}
        for pid in configs:
            key, env_name = resolve_api_key(pid)
            if env_name:
                seen[pid] = bool(key.strip())
        return jsonify(seen)

    @app.post("/api/provider/key")
    def provider_store_key() -> Response:
        data = _json_body()
        if data is None:
            return jsonify(_BODY_NOT_OBJECT), 400
        provider = data.get("provider", "")
        api_key = data.get("apiKey", "")
        if not provider or not isinstance(provider, str):
            return jsonify({"error": "provider is required", "code": "MISSING_PARAM"}), 400
        if not api_key or not isinstance(api_key, str):
            return jsonify({"error": "apiKey is required", "code": "MISSING_PARAM"}), 400
        try:
            stored, secure = _store_api_key(provider, api_key)
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

    @app.get("/api/provider/key-status")
    def provider_key_status() -> Response:
        provider = request.args.get("provider", "")
        if not provider:
            return jsonify({"error": "provider is required", "code": "MISSING_PARAM"}), 400
        return jsonify({"configured": get_api_key_secure(provider) is not None})

    @app.get("/api/known-models")
    def known_models() -> Response:
        return jsonify(get_known_models())

    @app.get("/api/provider-configs")
    def provider_configs() -> Response:
        return jsonify(get_provider_configs())
