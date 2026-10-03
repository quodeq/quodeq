"""Readers place findings with the same rule as the writers: requirement first."""
from __future__ import annotations

from pathlib import Path

from quodeq.core.events.models import Judgment
from quodeq.core.evidence.req_mapping import PrincipleResolver, group_judgments

_MAP = {"ACC-PER-01": "Perceivable", "ACC-OPR-01": "Operable"}
_RESOLVER = PrincipleResolver(_MAP, frozenset(_MAP.values()))


def test_the_requirement_wins_over_a_stale_principle() -> None:
    assert _RESOLVER.place("ACC-OPR-01", "Perceivable") == "Operable"


def test_an_unknown_requirement_falls_back_to_a_real_principle() -> None:
    assert _RESOLVER.place("ACC-OPR-99", "Operable") == "Operable"


def test_nothing_placeable_is_quarantined() -> None:
    assert _RESOLVER.place("ACC-OPR-99", "Not A Principle") is None
    assert _RESOLVER.place(None, None) is None


def test_without_a_standard_the_named_principle_passes_through() -> None:
    permissive = PrincipleResolver({}, frozenset())

    assert permissive.place("ANY-1", "Named") == "Named"
    assert permissive.place("ANY-1", None) == "ANY-1"


def test_resolve_keeps_its_single_id_meaning() -> None:
    assert _RESOLVER.resolve("acc-per-1") == "Perceivable"
    assert _RESOLVER.resolve("Operable") == "Operable"
    assert _RESOLVER.resolve("Nope") is None


def test_the_report_groups_by_the_requirements_principle() -> None:
    stale = Judgment(practice_id="Perceivable", verdict="violation", dimension="accessibility",
                     file="a.kt", line=1, reason="r", req="ACC-OPR-01", severity="major")

    grouped = group_judgments([stale], "accessibility",
                              req_map_reader=lambda _d, _dim: dict(_MAP), compiled_dir=Path("compiled"))

    assert list(grouped.violations) == ["Operable"]
