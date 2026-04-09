"""Classify previous findings into inline-verify vs mini-verify buckets."""
from __future__ import annotations


def classify_findings(
    needs_verify: list[dict],
    queue_files: set[str],
) -> tuple[list[dict], list[dict]]:
    """Split findings that need verification into two buckets.

    - **inline**: file is in the analysis queue — findings passed as prompt context
    - **mini_verify**: file is NOT in queue — needs separate post-analysis verification

    Returns (inline, mini_verify).
    """
    inline: list[dict] = []
    mini_verify: list[dict] = []
    for finding in needs_verify:
        if finding.get("file", "") in queue_files:
            inline.append(finding)
        else:
            mini_verify.append(finding)
    return inline, mini_verify
