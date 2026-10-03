"""admit places a finding in its standard, or says why it cannot."""
from __future__ import annotations

from quodeq.core.admission import (
    Admitted, FindingFacts, StandardCatalog, StandardIndex, Unmapped, UnmappedReason, admit,
)

_REFS = ({"source": "wcag22", "id": "1.1.1", "name": "Non-text Content"},)
_ACC = StandardIndex("accessibility", {
    "ACC-PER-01": "Perceivable", "ACC-PER-02": "Perceivable", "ACC-OPR-04": "Operable",
}, {"ACC-PER-01": _REFS})
_SEC = StandardIndex("security", {"S-CON-1": "Confidentiality"})
_CATALOG = StandardCatalog.of([_ACC, _SEC])


def _facts(**row) -> FindingFacts:
    return FindingFacts.from_wire({"t": "violation", "d": "accessibility", "file": "a.kt", "line": 3, **row})


def test_a_known_requirement_derives_principle_and_refs() -> None:
    result = admit(_facts(req="ACC-PER-01"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.dimension, result.req, result.principle) == ("accessibility", "ACC-PER-01", "Perceivable")
    assert result.refs == _REFS
    assert not result.folded and not result.routed


def test_a_near_miss_folds_onto_the_canonical_id() -> None:
    result = admit(_facts(req="acc-per-1"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.req, result.folded) == ("ACC-PER-01", True)


def test_a_code_of_another_loaded_dimension_is_routed_there() -> None:
    result = admit(_facts(req="S-CON-1"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.dimension, result.principle, result.routed) == ("security", "Confidentiality", True)


def test_an_unknown_code_is_unmapped_with_the_nearest_valid_ids() -> None:
    result = admit(_facts(req="ACC-PER-09"), _CATALOG)

    assert isinstance(result, Unmapped)
    assert result.reason is UnmappedReason.UNKNOWN_REQUIREMENT
    assert result.nearest[:2] == ("ACC-PER-02", "ACC-PER-01")


def test_a_model_supplied_principle_never_overrides_the_standard() -> None:
    result = admit(_facts(req="ACC-OPR-04", p="Perceivable"), _CATALOG)

    assert isinstance(result, Admitted)
    assert result.principle == "Operable"


def test_a_check_row_with_the_requirement_in_p_is_placed() -> None:
    result = admit(_facts(p="ACC-OPR-04"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.req, result.principle) == ("ACC-OPR-04", "Operable")


def test_a_legacy_row_naming_its_principle_is_placed_without_a_requirement() -> None:
    result = admit(_facts(p="Perceivable"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.req, result.principle) == (None, "Perceivable")


def test_no_code_and_no_usable_hint_is_unmapped() -> None:
    result = admit(_facts(p="N/A"), _CATALOG)

    assert isinstance(result, Unmapped)
    assert result.reason is UnmappedReason.MISSING_REQUIREMENT


def test_a_dimension_without_a_loaded_standard_is_unmapped_not_guessed() -> None:
    result = admit(_facts(req="ACC-PER-01", d="performance"), _CATALOG)

    assert isinstance(result, Unmapped)
    assert result.reason is UnmappedReason.NO_STANDARD


def test_an_ambiguous_near_miss_is_not_folded() -> None:
    index = StandardIndex("x", {"A-DEP-1": "One", "B-DEP-1": "Two"})
    result = admit(_facts(req="DEP-1", d="x"), StandardCatalog.of([index]))

    assert isinstance(result, Unmapped)
    assert result.reason is UnmappedReason.UNKNOWN_REQUIREMENT


def test_an_unknown_code_with_a_valid_principle_is_placed_by_it_and_flagged() -> None:
    """History counts where readers always counted it; the flag lets the live
    path still ask the model for a valid code."""
    result = admit(_facts(req="ACC-PER-99", p="Operable"), _CATALOG)

    assert isinstance(result, Admitted)
    assert (result.req, result.principle, result.unknown_req) == (None, "Operable", True)
