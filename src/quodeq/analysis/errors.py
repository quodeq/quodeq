"""Structured error types for the evaluation pipeline."""
from __future__ import annotations

import re


class EvaluationError(RuntimeError):
    """Base error for evaluation pipeline failures."""


class RepoNotFoundError(EvaluationError):
    """Repository path does not exist or is not accessible."""


class RepoCloneError(EvaluationError):
    """Failed to clone a remote repository."""


class NoSourceFilesError(EvaluationError):
    """No recognized source files found in the repository or scope."""


class ProviderError(EvaluationError):
    """AI provider failed (CLI exited with error, auth failure, etc.)."""


class FatalProviderError(ProviderError):
    """Provider failure that no retry can fix (quota exhausted, auth, billing).

    Raised so the run aborts once with a clear cause instead of respawning
    agents against a provider that will keep rejecting every call.
    ``reason`` is a short machine-readable code: "quota", "auth", "payment".
    """

    def __init__(self, message: str, *, reason: str = "provider_fatal") -> None:
        super().__init__(message)
        self.reason = reason


class BudgetExceededError(EvaluationError):
    """Evaluation exceeded the configured time or cost budget."""


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
