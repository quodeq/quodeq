"""Near-miss requirement IDs fold onto the standard's real IDs.

Local models emit IDs the standard does not define — the 2026-08-01
clean-architecture run alone quarantined ``CLEa-DEP-05`` (wrong case),
``CLE-TES-02``/``CLE-ENT-02`` (truncated prefix) and bare ``SEP-03``
(missing prefix). Each was a real finding thrown away over a typo.

The fold matches on the trailing ``(category, number)`` segments, so it can
never merge two genuinely different requirements: ``CLEA-DEP-01`` and
``CLEA-DEP-02`` differ in the number and stay distinct, even though they are
one character apart.
"""
from __future__ import annotations

from quodeq.core.evidence._req_mapping import PrincipleResolver, normalize_req_id

CANONICAL = ("CLEA-DEP-01", "CLEA-DEP-05", "CLEA-TES-02", "CLEA-SEP-03", "CLEA-ENT-02")


class TestNormalizeReqId:
    def test_exact_id_is_returned_unchanged(self):
        assert normalize_req_id("CLEA-DEP-05", CANONICAL) == "CLEA-DEP-05"

    def test_wrong_case_folds(self):
        assert normalize_req_id("CLEa-DEP-05", CANONICAL) == "CLEA-DEP-05"
        assert normalize_req_id("clea-dep-05", CANONICAL) == "CLEA-DEP-05"

    def test_truncated_prefix_folds(self):
        assert normalize_req_id("CLE-TES-02", CANONICAL) == "CLEA-TES-02"
        assert normalize_req_id("CLE-ENT-02", CANONICAL) == "CLEA-ENT-02"

    def test_missing_prefix_folds(self):
        assert normalize_req_id("SEP-03", CANONICAL) == "CLEA-SEP-03"

    def test_neighbouring_requirements_never_merge(self):
        """One edit apart, but a different requirement: must NOT fold."""
        assert normalize_req_id("CLEA-DEP-02", CANONICAL) is None
        assert normalize_req_id("CLEA-DEP-99", CANONICAL) is None

    def test_unknown_category_does_not_fold(self):
        assert normalize_req_id("CLEA-XXX-01", CANONICAL) is None

    def test_ambiguous_trailing_pair_refuses_to_fold(self):
        """Two standards sharing a category+number is not a typo we can resolve."""
        ambiguous = ("CLEA-SEP-03", "DDD-SEP-03")
        assert normalize_req_id("SEP-03", ambiguous) is None

    def test_blank_and_shapeless_inputs(self):
        assert normalize_req_id("", CANONICAL) is None
        assert normalize_req_id("nonsense", CANONICAL) is None
        assert normalize_req_id("CLEA-DEP-05", ()) is None


class TestResolverUsesTheFold:
    def _resolver(self):
        return PrincipleResolver(
            req_to_principle={"CLEA-DEP-05": "Dependency Rule",
                              "CLEA-SEP-03": "Separation of Concerns"},
            canonical=frozenset({"Dependency Rule", "Separation of Concerns"}),
        )

    def test_near_miss_id_resolves_instead_of_quarantining(self):
        assert self._resolver().resolve("CLEa-DEP-05") == "Dependency Rule"
        assert self._resolver().resolve("SEP-03") == "Separation of Concerns"

    def test_exact_ids_still_resolve(self):
        assert self._resolver().resolve("CLEA-DEP-05") == "Dependency Rule"

    def test_a_principle_name_still_resolves_directly(self):
        """Findings may name the principle rather than a requirement."""
        assert self._resolver().resolve("Dependency Rule") == "Dependency Rule"

    def test_genuinely_foreign_ids_still_quarantine(self):
        assert self._resolver().resolve("SEC-CON-1") is None
        assert self._resolver().resolve(None) is None

    def test_no_standard_stays_permissive(self):
        permissive = PrincipleResolver(req_to_principle={}, canonical=frozenset())
        assert permissive.resolve("ANYTHING-1") == "ANYTHING-1"
