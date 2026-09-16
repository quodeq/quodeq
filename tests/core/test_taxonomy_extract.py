"""extract_taxonomy() reads violation_types blocks and rejects malformed ones."""
from __future__ import annotations

import pytest

from quodeq.core.taxonomy import Taxonomy, TaxonomyError, extract_taxonomy


def _compiled(*reqs: dict, version: str = "2026-09-16") -> dict:
    return {
        "id": "reliability", "taxonomy_version": version,
        "principles": [{"name": "Fault Tolerance", "requirements": list(reqs)}],
    }


def test_reads_codes_aliases_and_version():
    tax = extract_taxonomy(_compiled({
        "id": "R-FT-1", "text": "...",
        "violation_types": [
            {"code": "empty-catch-block", "aliases": ["Empty_Catch", "silent-exception-swallow"]},
            {"code": "broad-exception-catch"},
        ],
    }))
    assert isinstance(tax, Taxonomy)
    assert tax.version == "2026-09-16"
    types = tax.for_requirement("R-FT-1")
    assert types.codes == ("empty-catch-block", "broad-exception-catch")
    assert types.aliases == {
        "empty-catch": "empty-catch-block",
        "silent-exception-swallow": "empty-catch-block",
    }


def test_requirement_without_block_is_omitted():
    tax = extract_taxonomy(_compiled({"id": "R-FT-2", "text": "..."}))
    assert tax.for_requirement("R-FT-2") is None
    assert tax.requirements == {}


def test_empty_dict_gives_empty_taxonomy():
    tax = extract_taxonomy({})
    assert tax.version == ""
    assert tax.requirements == {}


@pytest.mark.parametrize("block, message", [
    ([{"code": "other"}], "reserved"),
    ([{"code": "Empty_Catch"}], "kebab-case"),
    ([{"code": "a"}, {"code": "a"}], "duplicate"),
    ([{"code": "a", "aliases": ["x"]}, {"code": "b", "aliases": ["x"]}], "maps to both"),
    ([{"code": "a", "aliases": ["b"]}, {"code": "b"}], "both a code and an alias"),
    ([{"code": "a", "aliases": "x"}], "list of strings"),
    ("not-a-list", "must be a list"),
    ([{"nocode": 1}], "string 'code'"),
])
def test_rejects_malformed_blocks(block, message):
    with pytest.raises(TaxonomyError, match=message):
        extract_taxonomy(_compiled({"id": "R-FT-1", "violation_types": block}))
