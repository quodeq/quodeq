"""canonicalize() maps model tags onto a requirement's codes; fold() is its first step."""
from __future__ import annotations

import pytest

from quodeq.core.taxonomy import (
    EMPTY_TAXONOMY, OTHER, RequirementTypes, Taxonomy, canonicalize, fold,
)

FT1 = RequirementTypes(
    codes=("empty-catch-block", "broad-exception-catch", "missing-error-handling"),
    aliases={
        "empty-catch": "empty-catch-block",
        "silent-exception-swallow": "empty-catch-block",
        "generic-exception-catch": "broad-exception-catch",
    },
)
TAX = Taxonomy(version="2026-09-16", requirements={"R-FT-1": FT1})


@pytest.mark.parametrize("raw, expected", [
    ("Empty_Catch Block", "empty-catch-block"),
    ("  broad--exception.catch ", "broad-exception-catch"),
    ("", ""),
    (None, ""),
    (42, ""),
])
def test_fold(raw, expected):
    assert fold(raw) == expected


def test_exact_code_and_other_are_fixed_points():
    assert canonicalize(TAX, "R-FT-1", "empty-catch-block") == "empty-catch-block"
    assert canonicalize(TAX, "R-FT-1", OTHER) == OTHER


def test_alias_maps_to_code():
    assert canonicalize(TAX, "R-FT-1", "generic-exception-catch") == "broad-exception-catch"
    assert canonicalize(TAX, "R-FT-1", "Empty_Catch") == "empty-catch-block"


def test_token_fold_reaches_alias_and_code():
    # error -> exception synonym lands on the silent-exception-swallow alias
    assert canonicalize(TAX, "R-FT-1", "silent-error-swallow") == "empty-catch-block"
    # plural strip lands on the code itself
    assert canonicalize(TAX, "R-FT-1", "empty-catch-blocks") == "empty-catch-block"


def test_known_distinct_pair_stays_distinct():
    a = canonicalize(TAX, "R-FT-1", "empty-catch-block")
    b = canonicalize(TAX, "R-FT-1", "broad-exception-catch")
    assert a != b


def test_unmapped_tag_is_other():
    assert canonicalize(TAX, "R-FT-1", "unguarded-thread-spawn") == OTHER


@pytest.mark.parametrize("raw", ["", None, "   "])
def test_missing_tag_is_other(raw):
    assert canonicalize(TAX, "R-FT-1", raw) == OTHER
    assert canonicalize(EMPTY_TAXONOMY, "R-FT-1", raw) == OTHER


def test_requirement_without_types_returns_folded_tag():
    # Transitional behaviour before a taxonomy exists: only case and separators merge.
    assert canonicalize(TAX, "R-FT-9", "Silent_Fallback") == "silent-fallback"
    assert canonicalize(EMPTY_TAXONOMY, "R-FT-1", "Silent_Fallback") == "silent-fallback"
    assert canonicalize(TAX, None, "Silent_Fallback") == "silent-fallback"
