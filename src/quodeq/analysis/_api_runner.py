"""OpenAI SDK-based API runner for direct LLM evaluation.

Calls any OpenAI-compatible API (Ollama, OpenRouter, LM Studio, etc.)
and writes findings as JSONL evidence -- the same format the CLI runner
produces via MCP.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiRunnerConfig:
    """Configuration for a single API runner invocation."""

    model: str
    api_base: str
    api_key: str = ""
    temperature: float = 0.1
    max_tokens: int | None = None


def _parse_findings(raw: str) -> list[dict]:
    """Parse the LLM response into a list of finding dicts.

    Raises ValueError if the response is not valid JSON with a 'findings' key.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse LLM response as JSON: {exc}") from exc

    if isinstance(data, dict) and "findings" in data:
        findings = data["findings"]
        if isinstance(findings, list):
            return findings

    raise ValueError(
        "LLM response missing 'findings' array. "
        f"Got keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}"
    )


def run_api_analysis(
    *,
    prompt: str,
    jsonl_file: Path,
    config: ApiRunnerConfig,
) -> None:
    """Call an OpenAI-compatible API and write findings to JSONL.

    Raises ImportError if the openai package is not installed.
    Raises ValueError if the LLM response cannot be parsed.
    """
    if openai is None:
        raise ImportError(
            "The 'openai' package is required for API mode. "
            "Install it with: pip install 'quodeq[api]'"
        )

    client = openai.OpenAI(
        base_url=config.api_base,
        api_key=config.api_key,
    )

    create_kwargs: dict = dict(
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=config.temperature,
    )
    if config.max_tokens is not None:
        create_kwargs["max_tokens"] = config.max_tokens

    _log.info("Calling %s model=%s", config.api_base, config.model)
    response = client.chat.completions.create(**create_kwargs)

    raw_content = response.choices[0].message.content
    findings = _parse_findings(raw_content)

    _log.info("Received %d findings from API", len(findings))

    with open(jsonl_file, "w") as fh:
        for finding in findings:
            fh.write(json.dumps(finding) + "\n")
