"""quodeq.verifier — Plan 1 manifest + local LLM → structured verdict."""

from quodeq.verifier.errors import (
    MalformedResponseError,
    OllamaUnreachableError,
    VerifierError,
    VerifierTimeoutError,
)
from quodeq.verifier.models import (
    ChecklistAnswer,
    FindingExtraction,
    FindingsExtraction,
    Verdict,
    VerifierResponse,
    VerifierResult,
)
from quodeq.verifier.verifier import Verifier

__all__ = [
    "Verifier",
    "Verdict",
    "VerifierResponse",
    "VerifierResult",
    "ChecklistAnswer",
    "FindingExtraction",
    "FindingsExtraction",
    "VerifierError",
    "MalformedResponseError",
    "OllamaUnreachableError",
    "VerifierTimeoutError",
]
