"""_standards_refs: the shared index walk and the attach_* functions built on it."""
from __future__ import annotations

# tools/ is importable via conftest.py sys.path insert


def _index() -> dict[str, list[dict]]:
    return {
        "P1": [{"id": "A", "_cwe_ids": [521], "_cert_ids": [], "_wcag_ids": [], "refs": []}],
        "P2": [
            {"id": "B", "_cwe_ids": [], "_cert_ids": [], "_wcag_ids": ["1.1.1"], "refs": []},
            {"id": "C", "_cwe_ids": [79, 79], "_cert_ids": [], "_wcag_ids": [], "refs": []},
        ],
    }


def test_each_req_yields_every_requirement_across_practices():
    from _standards_refs import _each_req

    assert [r["id"] for r in _each_req(_index())] == ["A", "B", "C"]


def test_each_req_is_empty_for_an_empty_index():
    from _standards_refs import _each_req

    assert list(_each_req({})) == []


def test_attach_cwe_refs_adds_one_ref_per_cwe_id():
    from _standards_refs import attach_cwe_refs

    index = _index()
    attach_cwe_refs(index, None, lambda db, cid: f"name-{cid}")

    assert index["P1"][0]["refs"] == [{
        "source": "cwe", "id": "521", "name": "CWE-521",
        "url": "https://cwe.mitre.org/data/definitions/521.html",
    }]
    assert index["P2"][0]["refs"] == []
    # no dedup on this path: the ID appears twice, so the ref does too
    assert len(index["P2"][1]["refs"]) == 2


def test_attach_wcag_refs_skips_a_non_usability_dimension(tmp_path):
    from _standards_refs import attach_wcag_refs

    index = _index()
    attach_wcag_refs(index, tmp_path, "security")
    assert all(not req["refs"] for reqs in index.values() for req in reqs)


def test_attach_wcag_refs_attaches_matching_criteria(tmp_path):
    import json

    from _standards_refs import attach_wcag_refs

    wcag = tmp_path / "wcag"
    wcag.mkdir()
    (wcag / "level_a.json").write_text(json.dumps(
        {"criteria": [{"id": "1.1.1", "name": "Non-text Content", "url": "https://x/1.1.1"}]}))

    index = _index()
    attach_wcag_refs(index, tmp_path, "usability")

    assert index["P2"][0]["refs"] == [{
        "source": "wcag22", "id": "1.1.1",
        "name": "Non-text Content", "url": "https://x/1.1.1",
    }]
