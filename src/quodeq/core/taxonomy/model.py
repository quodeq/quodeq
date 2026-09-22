"""Canonical violation-type taxonomy: value objects only, no IO."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

# Reserved code for tags no declared type accepts. Never declared in a
# standards file; one such type per requirement replaces "one type per
# untagged finding" once PR B wires the tally.
OTHER = "other"


@dataclass(frozen=True, slots=True)
class RequirementTypes:
    """Allowed codes for one requirement plus its folded alias map."""

    codes: tuple[str, ...] = ()
    aliases: Mapping[str, str] = field(default_factory=dict)  # folded alias -> code


@dataclass(frozen=True, slots=True)
class Taxonomy:
    """Per-requirement allowed violation-type codes for one dimension."""

    version: str = ""
    requirements: Mapping[str, RequirementTypes] = field(default_factory=dict)

    def for_requirement(self, req_id: str | None) -> RequirementTypes | None:
        """The allowed types for one requirement, or None if it declares none.

        None is also the answer for a missing *req_id*, so a finding's raw
        requirement can be passed straight through without a guard.
        """
        if not req_id:
            return None
        return self.requirements.get(req_id)


EMPTY_TAXONOMY = Taxonomy()
