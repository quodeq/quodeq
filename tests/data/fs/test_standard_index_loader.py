"""The index's mapping stamp and the on-disk loader."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.core.admission import StandardIndex
from quodeq.data.fs.standard_index_loader import load_standard_catalog, load_standard_index


def test_the_stamp_ignores_wording_but_follows_the_mapping() -> None:
    base = StandardIndex("d", {"R-1": "P"}, {"R-1": ({"source": "cwe", "id": "1", "name": "a"},)})
    reworded = StandardIndex("d", {"R-1": "P"}, {"R-1": ({"source": "cwe", "id": "1", "name": "b"},)})
    moved = StandardIndex("d", {"R-1": "Q"}, {"R-1": ({"source": "cwe", "id": "1", "name": "a"},)})

    assert base.mapping_stamp == reworded.mapping_stamp
    assert base.mapping_stamp != moved.mapping_stamp


def _write(directory: Path, dimension: str, principle: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{dimension}.json").write_text(json.dumps({"principles": [
        {"name": principle, "requirements": [{"id": "R-1", "text": "t", "refs": [{"source": "cwe", "id": "1"}]}]},
    ]}), encoding="utf-8")


def test_a_custom_evaluator_wins_over_the_compiled_standard(tmp_path: Path) -> None:
    _write(tmp_path / "compiled", "dim", "Built-in")
    _write(tmp_path / "evaluators", "dim", "Custom")

    index = load_standard_index("dim", evaluators_dir=tmp_path / "evaluators", compiled_dir=tmp_path / "compiled")

    assert index is not None and index.req_to_principle == {"R-1": "Custom"}


def test_a_missing_or_malformed_standard_gives_no_index(tmp_path: Path) -> None:
    (tmp_path / "bad.json").write_text("{nope", encoding="utf-8")

    assert load_standard_index("bad", evaluators_dir=None, compiled_dir=tmp_path) is None
    assert load_standard_index("absent", evaluators_dir=None, compiled_dir=tmp_path) is None


def test_every_bundled_standard_loads_into_the_catalog() -> None:
    import quodeq

    data = Path(quodeq.__file__).parent / "data"
    registry = json.loads((data / "config" / "dimensions.json").read_text(encoding="utf-8"))
    ids = [d["id"] for d in registry["applies"]]

    catalog = load_standard_catalog(ids, evaluators_dir=None, compiled_dir=data / "standards" / "compiled")

    assert sorted(catalog.indexes) == sorted(ids)
    assert len(catalog.get("accessibility").req_to_principle) == 35


def test_admission_agrees_with_the_reader_resolver_on_every_bundled_requirement() -> None:
    """Readers still resolve on their own; admit must never disagree with them."""
    import quodeq
    from quodeq.core.admission import Admitted, FindingFacts, admit
    from quodeq.core.evidence.req_mapping import build_principle_resolver
    from quodeq.data.fs.standards_loader import read_req_to_principle_map

    compiled = Path(quodeq.__file__).parent / "data" / "standards" / "compiled"
    dims = [p.stem for p in compiled.glob("*.json")]
    catalog = load_standard_catalog(dims, evaluators_dir=None, compiled_dir=compiled)
    for dim in dims:
        resolver = build_principle_resolver(dim, None, compiled, req_map_reader=read_req_to_principle_map)
        for req in catalog.get(dim).req_to_principle:
            for variant in (req, req.lower()):
                facts = FindingFacts.from_wire({"req": variant, "d": dim, "t": "violation"})
                result = admit(facts, catalog)
                expected = resolver.resolve(variant)
                assert isinstance(result, Admitted), (dim, variant)
                assert result.principle == expected, (dim, variant)
