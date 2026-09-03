"""_default_api_base must not silently ignore an invalid CWE_API_BASE."""
from __future__ import annotations

# tools/ is importable via conftest.py sys.path insert


def test_invalid_scheme_prints_warning_and_falls_back(capsys):
    from audit_cwe_abstraction import _CWE_API_URL, _default_api_base

    result = _default_api_base({"CWE_API_BASE": "ftp://example.com/cwe"})

    assert result == _CWE_API_URL
    captured = capsys.readouterr()
    assert "ftp://example.com/cwe" in captured.out
    assert "CWE_API_BASE" in captured.out
