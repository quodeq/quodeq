"""Smoke tests for the verifier package."""


def test_verifier_package_importable():
    import quodeq.verifier  # noqa: F401


def test_httpx_available():
    import httpx  # noqa: F401


def test_pydantic_available():
    import pydantic  # noqa: F401
