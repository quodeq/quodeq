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


def _run_main_with_fetches(monkeypatch, fetched: dict[int, dict | None]) -> list[list[dict]]:
    """Run main() over CWEs *fetched* (None = failed fetch); return what it wrote."""
    import audit_cwe_abstraction as audit

    written: list[list[dict]] = []
    monkeypatch.setattr(audit, "get_all_cwes", lambda _dir: {cwe: ["security"] for cwe in fetched})
    monkeypatch.setattr(audit, "fetch_cwe_info", lambda cwe, _base: fetched[cwe])
    monkeypatch.setattr(audit.time, "sleep", lambda _s: None)
    monkeypatch.setattr(audit, "_write_results_json", lambda results: written.append(results))
    monkeypatch.setattr(audit.sys, "argv", ["audit_cwe_abstraction.py"])
    audit.main()
    return written


def _record(cwe_id: int) -> dict:
    return {"id": cwe_id, "name": "n", "abstraction": "Base", "status": "", "mapping_usage": "Allowed",
            "mapping_rationale": ""}


def test_a_failed_fetch_refuses_to_write_the_audit(monkeypatch, capsys):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        _run_main_with_fetches(monkeypatch, {20: _record(20), 79: None})
    assert excinfo.value.code != 0
    assert "1 of 2" in capsys.readouterr().err


def test_no_results_refuses_to_write_the_audit(monkeypatch):
    import pytest

    with pytest.raises(SystemExit) as excinfo:
        _run_main_with_fetches(monkeypatch, {})
    assert excinfo.value.code != 0


def test_all_fetches_ok_writes_the_audit(monkeypatch):
    written = _run_main_with_fetches(monkeypatch, {20: _record(20)})
    assert [r["id"] for r in written[0]] == [20]
