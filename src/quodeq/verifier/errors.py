"""Verifier domain errors."""


class VerifierError(Exception):
    """Base class for verifier errors."""


class OllamaUnreachableError(VerifierError):
    """Could not connect to the Ollama server."""


class VerifierTimeoutError(VerifierError):
    """Ollama did not respond within the timeout window."""


class MalformedResponseError(VerifierError):
    """Ollama returned a response we could not parse."""
