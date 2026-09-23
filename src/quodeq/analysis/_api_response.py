"""Response handling for the API runner: parse one completion's text into
validated findings, give snippetless findings one repair re-ask, and record
the call's drop accounting. Split from ``_api_call`` (request construction
and the raw round-trip) so each side stays within the size budget.
Requires the ``quodeq[api]`` extra: ``pip install 'quodeq[api]'``
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import httpx
import openai

from quodeq.analysis._api_schema import parse_findings
from quodeq.analysis._drop_stats import format_reasons as _format_drop_reasons
from quodeq.analysis._drop_stats import record as _record_drop_stats
from quodeq.config.analysis_env import finding_repair_disabled

_log = logging.getLogger(__name__)

# Instruction for the repair re-ask: the model already holds the source (the
# original user message) and its own snippetless findings (replayed as the
# assistant turn), so the only new information it needs is what to fix.
_REPAIR_PROMPT = (
    "Each finding in your previous message is missing the required `snippet` "
    "field, so it will be discarded. Re-emit exactly these findings, each "
    "completed with `snippet` copied VERBATIM from the source you were given: "
    "exact characters, one or a few contiguous lines, with `end_line` matching "
    "the last snippet line. Do not add new findings and do not change req, "
    "file or line. Omit any finding whose code you cannot quote. "
    'Return JSON as {"findings": [...]}.'
)

# Ceiling on how many snippetless findings one repair call replays. A call
# that dropped more than this is a runaway (the qwen3.8 pattern averaged ~6
# per call); replaying hundreds would blow the context that produced the
# problem in the first place.
_MAX_REPAIR_FINDINGS = 25

# The reason key _record_drop_reason produces for a missing required snippet;
# the repair pass credits recoveries back against this bucket.
_SNIPPET_MISSING_REASON = "snippet:missing"


def _snippetless(dropped_nodes: list[dict]) -> list[dict]:
    """The dropped finding attempts a repair re-ask could plausibly save.

    A node qualifies when its ``snippet`` is absent or not a non-empty string
    and it still carries the identity fields (``req``, ``file``) the repair
    prompt pins. Nodes that failed with a snippet present failed for some
    other reason; re-asking about the snippet cannot help them.
    """
    out: list[dict] = []
    for node in dropped_nodes:
        snippet = node.get("snippet")
        if isinstance(snippet, str) and snippet:
            continue
        if not (node.get("req") and node.get("file")):
            continue
        out.append(node)
    return out


def _finding_identity(finding: dict) -> tuple:
    """Dedup key for merging repaired findings back into the kept list."""
    return (
        finding.get("req"), finding.get("file"), finding.get("line"), finding.get("t"),
    )


def repair_snippetless(
    client: openai.OpenAI,
    create_kwargs: dict,
    model: str,
    repairable: list[dict],
) -> list[dict]:
    """One follow-up call asking the model to complete its own snippetless
    findings. Returns the validated findings it came back with; ``[]`` on any
    failure -- the original call already succeeded, so a failed repair loses
    nothing that was not already lost. Never recurses: findings still missing
    a snippet after this are dropped for good, exactly as the schema says.
    """
    batch = repairable[:_MAX_REPAIR_FINDINGS]
    if len(batch) < len(repairable):
        _log.info(
            "Model %s: repair re-ask capped at %d of %d snippetless finding(s)",
            model, len(batch), len(repairable),
        )
    kwargs = dict(create_kwargs)
    kwargs["messages"] = [
        *create_kwargs["messages"],
        {
            "role": "assistant",
            "content": json.dumps({"findings": batch}, ensure_ascii=False),
        },
        {"role": "user", "content": _REPAIR_PROMPT},
    ]
    start = time.monotonic()
    try:
        response = client.chat.completions.create(**kwargs)
    except (openai.OpenAIError, httpx.HTTPError) as exc:
        _log.warning(
            "Model %s: repair re-ask failed after %.0fs, keeping first-pass "
            "findings only: %s",
            model, time.monotonic() - start, str(exc)[:300],
        )
        return []
    choice = response.choices[0] if response.choices else None
    text = (choice.message.content or "") if choice else ""
    findings, _ = parse_findings(text)
    return findings


def _merge_repaired(
    findings: list[dict], repaired: list[dict], asked: list[dict],
) -> int:
    """Append repaired findings not already kept; returns how many were added.

    Only findings answering the *asked* nodes are accepted, matched on
    (req, file): the repair prompt forbids new findings, and this makes
    that a property of the merge rather than a hope about the model. The
    match deliberately excludes ``line``, which the model may legitimately
    adjust to the snippet span it quotes, and ``t``, which a malformed node
    may not have carried at all. Full-identity dedup against the kept list
    stops a re-emitted duplicate from doubling.
    """
    allowed = {(n.get("req"), n.get("file")) for n in asked}
    seen = {_finding_identity(f) for f in findings}
    added = 0
    for finding in repaired:
        if (finding.get("req"), finding.get("file")) not in allowed:
            continue
        key = _finding_identity(finding)
        if key in seen:
            continue
        seen.add(key)
        findings.append(finding)
        added += 1
    return added


def _apply_repair(
    findings: list[dict],
    dropped: int,
    dropped_nodes: list[dict],
    drop_reasons: dict[str, int],
    reask: Callable[[list[dict]], list[dict]],
    model: str,
) -> int:
    """Run the repair re-ask over the snippetless drops; returns the adjusted
    dropped count. Recovered findings are appended to *findings* and credited
    back against the ``snippet:missing`` reason bucket, so the per-call log
    and the run-wide drop stats describe the final outcome, not the first
    attempt.
    """
    repairable = _snippetless(dropped_nodes)
    if not repairable:
        return dropped
    recovered = _merge_repaired(findings, reask(repairable), repairable)
    if not recovered:
        return dropped
    remaining = drop_reasons.get(_SNIPPET_MISSING_REASON, 0) - recovered
    if remaining > 0:
        drop_reasons[_SNIPPET_MISSING_REASON] = remaining
    else:
        drop_reasons.pop(_SNIPPET_MISSING_REASON, None)
    _log.info(
        "Model %s: repair re-ask recovered %d of %d snippetless finding(s)",
        model, recovered, len(repairable),
    )
    # One asked node can come back as several grounded findings (distinct
    # lines under one req/file), so clamp at zero.
    return max(0, dropped - recovered)


def finish_call(
    model: str,
    finish_reason: str | None,
    text: str,
    start: float,
    *,
    reask: Callable[[list[dict]], list[dict]] | None = None,
) -> tuple[list[dict], bool]:
    """Parse *text*, attempt a snippet repair re-ask, record drop stats and
    log the call's outcome.

    Returns ``(findings, was_lossy)``. ``was_lossy`` is True when the
    response was truncated by the output budget (``finish_reason ==
    "length"``), so findings past the cut are lost. See ``_call_api`` for
    the full lossy-vs-dropped contract.

    *reask*, when supplied, takes the snippetless dropped nodes and returns
    whatever validated findings a single repair call recovers.
    QUODEQ_DISABLE_FINDING_REPAIR is the operator kill switch.
    """
    drop_reasons: dict[str, int] = {}
    dropped_nodes: list[dict] = []
    findings, dropped = parse_findings(
        text, drop_reasons=drop_reasons, dropped_sink=dropped_nodes,
    )
    if dropped and reask is not None and not finding_repair_disabled():
        dropped = _apply_repair(
            findings, dropped, dropped_nodes, drop_reasons, reask, model,
        )
    elapsed = time.monotonic() - start
    # Feed the per-run aggregate so the dimension loops can report ONE
    # drop-ratio signal at end of run instead of N scattered per-call lines.
    _record_drop_stats(dropped=dropped, kept=len(findings), reasons=drop_reasons)

    # A length-truncated response is an incomplete analysis: the model ran out of
    # output budget mid-stream, so findings after the cut are simply gone. Treat
    # it as lossy so run_api_analysis writes an 'error' marker and the file(s)
    # re-dispatch next run, rather than caching a partial result as 'ok'.
    truncated = finish_reason == "length"
    if truncated:
        _log.warning(
            "Model %s response was truncated (finish_reason=length) after %.0fs; "
            "kept %d finding(s) but the analysis is incomplete and will re-dispatch. "
            "Reduce input size or raise the model context window.",
            model, elapsed, len(findings),
        )
    if dropped:
        _log.warning(
            "Model %s: dropped %d malformed finding(s) of %d parsed in %.0fs "
            "(kept %d) -- %s. The call succeeded; malformed findings were discarded.",
            model, dropped, dropped + len(findings), elapsed, len(findings),
            _format_drop_reasons(drop_reasons),
        )
    _log.debug(
        "Model %s returned %d valid findings in %.0fs (raw bytes: %d)",
        model, len(findings), elapsed, len(text),
    )
    return findings, truncated
