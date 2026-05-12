"""Verifier domain errors."""


class VerifierError(Exception):
    """Base class for verifier errors."""


class LLMUnreachableError(VerifierError):
    """Could not connect to the LLM server."""


class VerifierTimeoutError(VerifierError):
    """Ollama did not respond within the timeout window."""


class MalformedResponseError(VerifierError):
    """Ollama returned a response we could not parse."""
