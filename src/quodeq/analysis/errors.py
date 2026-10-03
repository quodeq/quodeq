"""Structured error types for the evaluation pipeline."""
from __future__ import annotations

import re

from quodeq.core.stream.events import COPILOT_MCP_POLICY_REASON

# Cancel-cause / interruption-reason codes shared by the pool workers and
# scalers that raise them, the dim-runner circuit breaker, and the loop
# guards / CLI lifecycle that read them back via cancellation.cancel_reason()
# or interruption_reason(). Every consumer imports these rather than
# retyping the string, so a rename here can't silently desync a comparison.
REASON_PROVIDER_FATAL = "provider_fatal"
REASON_AGENT_FAILURE_STREAK = "agent_failure_streak"
REASON_CIRCUIT_BREAKER = "circuit_breaker"
REASON_CANCELLED_SIGNAL = "cancelled_signal"
REASON_FAILED_EXCEPTION = "failed_exception"


class EvaluationError(RuntimeError):
    """Base error for evaluation pipeline failures."""


class ProviderError(EvaluationError):
    """AI provider failed (CLI exited with error, auth failure, etc.)."""


class FatalProviderError(ProviderError):
    """Provider failure that no retry can fix (quota exhausted, auth, billing).

    Raised so the run aborts once with a clear cause instead of respawning
    agents against a provider that will keep rejecting every call.
    ``reason`` is a machine-readable code such as "quota", "auth",
    "payment", "policy", or "copilot_mcp_policy".
    """

    def __init__(self, message: str, *, reason: str = REASON_PROVIDER_FATAL) -> None:
        super().__init__(message)
        self.reason = reason


def provider_exit_reason(reason: str | None) -> str:
    """Map a provider reason or cancellation cause to its persistent exit code."""
    if reason and reason.startswith(f"{REASON_PROVIDER_FATAL}:"):
        reason = reason.split(":", 2)[1]
    return COPILOT_MCP_POLICY_REASON if reason == COPILOT_MCP_POLICY_REASON else REASON_PROVIDER_FATAL


# classify_fatal_provider_message's reason codes that _api_call.py's own
# 429/402 classification also produces, so both paths agree on the same
# value. "auth" and "policy" are produced here too but never compared
# elsewhere, so they stay bare.
REASON_QUOTA = "quota"
REASON_PAYMENT = "payment"

# Fatal-message classification shared by the CLI path (stderr of the claude/
# codex/gemini CLIs) and the API path (429 bodies). Patterns are deliberately
# conservative: a false "fatal" aborts the whole run, while a miss only means
# the pool-level failure-streak backstop stops the spawning a few agents
# later. High precision over recall.
_FATAL_MESSAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (reason, re.compile(pattern, re.IGNORECASE))
    for reason, pattern in (
        ("quota", r"insufficient[_ ]quota"),
        ("quota", r"exceeded your current quota"),
        ("quota", r"quota (has been )?exceeded"),
        ("quota", r"usage limit reached"),
        ("quota", r"out of credits"),
        ("payment", r"credit balance is too low"),
        ("payment", r"insufficient credits"),
        ("payment", r"payment required"),
        ("payment", r"billing hard limit"),
        ("auth", r"invalid api key"),
        ("auth", r"api key not (found|valid|set)"),
        ("auth", r"authentication (error|failed)"),
        ("auth", r"401 unauthorized"),
        ("auth", r"oauth token (has )?(expired|been revoked)"),
        ("auth", r"please run /login"),
    )
)


def classify_fatal_provider_message(text: str) -> str | None:
    """Return a fatal reason code ("quota", "auth", "payment") found in *text*.

    Returns None when the text matches no known unrecoverable-failure
    message, i.e. the failure should be treated as transient.
    """
    if not text:
        return None
    for reason, pattern in _FATAL_MESSAGE_PATTERNS:
        if pattern.search(text):
            return reason
    return None
