"""core.evidence receives config/data from callers instead of fetching it.

Covers the clean-architecture fixes: the CWE URL template is passed in (core
never reads the environment), and the req-to-principle map comes from an
injected reader (core never reads files).
"""
from __future__ import annotations

from pathlib import Path

from quodeq.core.evidence._refs import _CWE_URL_TEMPLATE_DEFAULT, resolve_llm_refs
from quodeq.core.evidence._req_mapping import (
    _resolve_req_to_principle_map,
    build_principle_resolver,
)


def test_resolve_llm_refs_uses_passed_template(monkeypatch):
    monkeypatch.setenv("QUODEQ_CWE_URL_TEMPLATE", "https://env.example/{cwe_id}")
    refs = resolve_llm_refs(["CWE-89"], None,
                            cwe_url_template="https://passed.example/{cwe_id}.html")
    assert refs == [{"label": "CWE-89", "url": "https://passed.example/89.html"}]


def test_resolve_llm_refs_default_ignores_environment(monkeypatch):
    # Core falls back to its packaged constant; only outer layers may honor
    # the env override (quodeq.config.evidence_env.cwe_url_template).
    monkeypatch.setenv("QUODEQ_CWE_URL_TEMPLATE", "https://env.example/{cwe_id}")
    refs = resolve_llm_refs(["CWE-89"], None)
    assert refs == [{"label": "CWE-89",
                     "url": _CWE_URL_TEMPLATE_DEFAULT.format(cwe_id="89")}]


def test_req_map_without_reader_does_no_io(tmp_path):
    # A directory that would explode if listed/read: point at a file instead.
    bogus = tmp_path / "not-a-dir.json"
    bogus.write_text("{")
    assert _resolve_req_to_principle_map("security", bogus, bogus) == {}
    resolver = build_principle_resolver("security", bogus, bogus)
    assert resolver.resolve("ANY-1") is None or isinstance(resolver.resolve("ANY-1"), str)


def test_req_map_reader_is_the_only_data_source(tmp_path):
    calls: list[tuple[Path, str]] = []

    def reader(directory: Path, dimension: str) -> dict[str, str] | None:
        calls.append((directory, dimension))
        return {"S-1": "Auth"} if directory.name == "evaluators" else None

    mapping = _resolve_req_to_principle_map(
        "security", tmp_path / "evaluators", tmp_path / "compiled",
        req_map_reader=reader,
    )
    assert mapping == {"S-1": "Auth"}
    assert calls == [(tmp_path / "evaluators", "security")]
