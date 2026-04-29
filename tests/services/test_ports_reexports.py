"""Verify the services layer re-exports new data-layer protocols."""


def test_findings_repository_re_exported():
    from quodeq.services.ports import FindingsRepository  # noqa: F401
