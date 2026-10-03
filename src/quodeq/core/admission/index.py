"""A standard's requirement map, as admission reads it."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from quodeq.core.admission.ids import id_shape, normalize_req_id

_NEAREST_MAX = 5  # hint length sent back to a model that used an unknown code
_FAR = 10**9  # sort key for ids with no comparable number


def _ref_identity(ref: dict) -> tuple[str, str]:
    return (str(ref.get("source") or ""), str(ref.get("id") or ref.get("label") or ""))


@dataclass(frozen=True)
class StandardIndex:
    """One dimension's standard: requirement ids, their principles and refs.

    ``mapping_stamp`` hashes what admission derives from (ids, principles and
    ref identities), not requirement wording, so rewording a requirement never
    forces findings to be re-derived.
    """

    dimension: str
    req_to_principle: Mapping[str, str]
    req_refs: Mapping[str, tuple[dict, ...]] = field(default_factory=dict)
    _ids: tuple[str, ...] = field(init=False, repr=False, compare=False)
    _principles: frozenset[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_ids", tuple(self.req_to_principle))
        object.__setattr__(self, "_principles", frozenset(self.req_to_principle.values()))

    @property
    def principles(self) -> frozenset[str]:
        """Every principle name the standard defines."""
        return self._principles

    def canonical(self, raw: str | None) -> tuple[str, bool] | None:
        """``(canonical id, folded)`` for *raw*, or None when the standard lacks it."""
        if not raw:
            return None
        if raw in self.req_to_principle:
            return raw, False
        folded = normalize_req_id(raw, self._ids)
        return (folded, True) if folded is not None else None

    def refs_for(self, req: str) -> tuple[dict, ...]:
        """The refs the standard attaches to canonical requirement *req*."""
        return tuple(self.req_refs.get(req, ()))

    def nearest(self, raw: str | None) -> tuple[str, ...]:
        """Valid ids closest to *raw*: same category first, then number distance."""
        shape = id_shape(raw or "")
        if shape is None:
            return self._ids[:_NEAREST_MAX]
        category, number = shape

        def distance(candidate: str) -> tuple[int, int, str]:
            other = id_shape(candidate)
            if other is None:
                return (2, _FAR, candidate)
            same = 0 if other[0] == category else 1
            return (same, abs(int(other[1]) - int(number)), candidate)

        return tuple(sorted(self._ids, key=distance)[:_NEAREST_MAX])

    @property
    def mapping_stamp(self) -> str:
        """SHA-256 of the requirement map and ref identities (see class docstring)."""
        payload = {
            "dimension": self.dimension,
            "map": sorted(self.req_to_principle.items()),
            "refs": sorted(
                (req, sorted(_ref_identity(r) for r in refs)) for req, refs in self.req_refs.items()
            ),
        }
        return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class StandardCatalog:
    """The loaded standards of a run, by dimension (lower-cased)."""

    indexes: Mapping[str, StandardIndex]

    @classmethod
    def of(cls, indexes: Iterable[StandardIndex]) -> StandardCatalog:
        """A catalog keyed by each index's lower-cased dimension."""
        return cls({i.dimension.lower(): i for i in indexes})

    def get(self, dimension: str | None) -> StandardIndex | None:
        """The index for *dimension*, case-insensitive, or None when not loaded."""
        return self.indexes.get((dimension or "").lower())

    def only(self, dimensions: Iterable[str]) -> StandardCatalog:
        """This catalog limited to *dimensions* (case-insensitive)."""
        keep = {d.lower() for d in dimensions}
        return StandardCatalog({d: i for d, i in self.indexes.items() if d in keep})

    def owner_of(self, req: str, *, besides: str | None) -> StandardIndex | None:
        """The one other dimension whose standard defines *req* exactly, if any."""
        skip = (besides or "").lower()
        owners = [i for d, i in self.indexes.items() if d != skip and req in i.req_to_principle]
        return owners[0] if len(owners) == 1 else None
