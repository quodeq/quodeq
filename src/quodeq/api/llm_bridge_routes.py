"""API routes for LLM bridge — provider status, models, testing."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from quodeq.llm_bridge import (
    get_ollama_status,
    list_ollama_models,
    estimate_max_agents,
    run_concurrency_test,
    get_known_models,
    get_provider_configs,
    check_cloud_connection,
)
from quodeq.shared.url_validation import validate_url_safe


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
        data = request.get_json() or {}
        model = data.get("model", "")
        if not model or not isinstance(model, str):
            return jsonify({"error": "model is required"}), 400
        if "\\" in model or ".." in model or "\0" in model:
            return jsonify({"error": "Invalid model name"}), 400
        result = run_concurrency_test(model)
        return jsonify(result)

    @app.post("/api/ollama/estimate-agents")
    def ollama_estimate_agents() -> Response:
        data = request.get_json() or {}
        model_size = data.get("model_size", 0)
        gpu_memory = data.get("gpu_memory", 0)
        return jsonify(estimate_max_agents(model_size=model_size, gpu_memory=gpu_memory))

    @app.post("/api/provider/test")
    def provider_test() -> Response:
        data = request.get_json() or {}
        api_base = data.get("api_base", "")
        if api_base:
            try:
                validate_url_safe(api_base, allow_private=True)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        result = check_cloud_connection(
            api_base=api_base,
            model=data.get("model", ""),
            api_key=data.get("api_key", ""),
        )
        return jsonify(result)

    @app.get("/api/known-models")
    def known_models() -> Response:
        return jsonify(get_known_models())

    @app.get("/api/provider-configs")
    def provider_configs() -> Response:
        return jsonify(get_provider_configs())
