"""Pure extraction of a Taxonomy from a compiled-standards dict.

Mirrors ``core/standards/refs.py:extract_requirements``: the IO counterpart
is ``data/fs/standards_loader.py:load_taxonomy``.
"""
from __future__ import annotations

import re

from quodeq.core.taxonomy._fold import fold
from quodeq.core.taxonomy.model import OTHER, RequirementTypes, Taxonomy

_KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class TaxonomyError(ValueError):
    """A compiled standards file declares an invalid violation_types block."""


def _code_entry(req_id: str, entry: object) -> tuple[str, list[str]]:
    if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
        raise TaxonomyError(f"{req_id}: each violation_types entry needs a string 'code'")
    code = entry["code"]
    if code == OTHER or not _KEBAB.match(code):
        raise TaxonomyError(f"{req_id}: invalid code {code!r} (kebab-case, 'other' is reserved)")
    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise TaxonomyError(f"{req_id}: aliases of {code!r} must be a list of strings")
    return code, aliases


def _add_aliases(req_id: str, code: str, aliases: list[str], alias_map: dict[str, str]) -> None:
    for alias in aliases:
        folded = fold(alias)
        if folded == OTHER:
            raise TaxonomyError(f"{req_id}: alias {alias!r} of {code!r} uses the reserved code 'other'")
        if not folded or not _KEBAB.match(folded):
            raise TaxonomyError(f"{req_id}: alias {alias!r} of {code!r} is not kebab-case")
        if folded in alias_map and alias_map[folded] != code:
            raise TaxonomyError(
                f"{req_id}: alias {alias!r} maps to both {alias_map[folded]!r} and {code!r}"
            )
        alias_map[folded] = code


def _requirement_types(req_id: str, raw: list) -> RequirementTypes:
    codes: list[str] = []
    alias_map: dict[str, str] = {}
    for entry in raw:
        code, aliases = _code_entry(req_id, entry)
        if code in codes:
            raise TaxonomyError(f"{req_id}: duplicate code {code!r}")
        codes.append(code)
        _add_aliases(req_id, code, aliases, alias_map)
    for folded, code in alias_map.items():
        if folded in codes and folded != code:
            raise TaxonomyError(f"{req_id}: {folded!r} is both a code and an alias of {code!r}")
    return RequirementTypes(codes=tuple(codes), aliases=alias_map)


def extract_taxonomy(data: dict) -> Taxonomy:
    """Build a Taxonomy from a compiled-standards dict.

    Requirements without a ``violation_types`` key are omitted, so
    ``canonicalize`` treats them as untyped. Raises TaxonomyError on a
    malformed block; tests/data/test_compiled_standards_taxonomy.py walks
    every shipped file.
    """
    requirements: dict[str, RequirementTypes] = {}
    for principle in data.get("principles", []):
        for req in principle.get("requirements", []):
            req_id = req.get("id")
            raw = req.get("violation_types")
            if not req_id or raw is None:
                continue
            if not isinstance(raw, list):
                raise TaxonomyError(f"{req_id}: violation_types must be a list")
            requirements[req_id] = _requirement_types(req_id, raw)
    version = data.get("taxonomy_version", "")
    return Taxonomy(version=str(version) if version else "", requirements=requirements)
