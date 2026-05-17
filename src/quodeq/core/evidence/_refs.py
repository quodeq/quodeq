"""Reference resolution helpers for evidence judgments."""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from quodeq.core.standards.refs import load_compiled_refs
from quodeq.core.types.req_ref import ReqRef

if TYPE_CHECKING:
    from quodeq.core.events.models import Judgment

_CWE_URL_TEMPLATE_DEFAULT = "https://cwe.mitre.org/data/definitions/{cwe_id}.html"


def _cwe_url_template(env: dict[str, str] | None = None) -> str:
    """Return the CWE URL template, reading from env lazily.

    *env* overrides ``os.environ`` when provided (e.g. for testing).
    When ``None``, falls back to ``os.environ``.
    """
    return (env if env is not None else os.environ).get(
        "QUODEQ_CWE_URL_TEMPLATE",
        _CWE_URL_TEMPLATE_DEFAULT,
    )


def build_req_refs_lookup(compiled_dir: Path, dimension: str) -> dict[str, list[dict]]:
    """Return {req_id: [{label, url}, ...]} for all refs of each requirement.

    Delegates to _ref_utils.load_compiled_refs for the heavy lifting.
    """
    return load_compiled_refs(str(compiled_dir), dimension)


def resolve_llm_refs(
    llm_refs: list[str] | None,
    all_req_refs: list[dict] | None,
    cwe_url_template: str | None = None,
) -> list[dict] | None:
    """Filter req_refs to only those the LLM selected, building URLs for unknown labels.

    Only refs that carry a ``url`` are kept.  When the LLM did not select
    any refs (``llm_refs`` is None/empty), returns ``None`` rather than
    dumping all compiled refs -- showing none is better than showing noise.

    *cwe_url_template* may be overridden for offline or internal deployments.
    """
    if not llm_refs:
        return None
    if cwe_url_template is None:
        cwe_url_template = _cwe_url_template()
    by_label = {r["label"]: r for r in (all_req_refs or [])}
    result = []
    upper_labels = {k.upper(): r for k, r in by_label.items()}
    for label in llm_refs:
        if label in by_label:
            result.append(by_label[label])
        elif label.upper().startswith("CWE-"):
            cwe_id = label.split("-", 1)[1]
            result.append({"label": label.upper(), "url": cwe_url_template.format(cwe_id=cwe_id)})
        else:
            # Prefix match: "CISQ-ASCRM-CWE-396" matches known label "CISQ"
            label_upper = label.upper()
            matched = next((r for k, r in upper_labels.items() if label_upper.startswith(k)), None)
            if matched:
                result.append(matched)
    # Only keep refs that have a URL -- drop bare labels without links
    result = [r for r in result if r.get("url")]
    return result if result else None


def enrich_judgment(
    j: "Judgment",
    llm_refs: list[str] | None,
    compiled_dir: Path | None,
    req_refs_cache: dict[str, dict[str, list[dict]]],
) -> "Judgment":
    """Resolve req_refs for a Judgment, returning the (possibly new) Judgment.

    Judgment is frozen (Pydantic), so we return a model_copy when we have
    something new to attach. When the judgment already carries refs, or no
    refs were resolved, the original instance is returned unchanged.
    """
    if j.req_refs:
        return j  # MCP server already enriched
    all_req_refs = None
    if compiled_dir and j.req and j.dimension:
        if j.dimension not in req_refs_cache:
            req_refs_cache[j.dimension] = build_req_refs_lookup(compiled_dir, j.dimension)
        all_req_refs = req_refs_cache[j.dimension].get(j.req)
    resolved = resolve_llm_refs(llm_refs, all_req_refs)
    if not resolved:
        return j
    refs = [ReqRef(label=r.get("label", ""), url=r.get("url", "")) for r in resolved]
    return j.model_copy(update={"req_refs": refs})
