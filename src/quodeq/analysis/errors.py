"""Structured error types for the evaluation pipeline."""
from __future__ import annotations


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


class BudgetExceededError(EvaluationError):
    """Evaluation exceeded the configured time or cost budget."""
