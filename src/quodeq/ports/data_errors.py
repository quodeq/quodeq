"""Domain-specific exception hierarchy for data access errors."""

from __future__ import annotations


class DataError(Exception):
    """Base exception for all data access errors."""


class AuthError(DataError):
    """Raised when authentication or authorization fails."""


class NotFoundError(DataError):
    """Raised when the requested resource does not exist."""


class NetworkError(DataError):
    """Raised when a network request fails."""


class ServerError(DataError):
    """Raised when the remote server returns an error."""


class InvalidDataError(DataError):
    """Raised when received data is malformed or invalid."""
