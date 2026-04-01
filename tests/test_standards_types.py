from pathlib import Path

from quodeq.config.paths import ConfigPaths
from quodeq.core.types.standard import StandardMeta, StandardDetail, StandardReference


def test_standard_meta_creation():
    meta = StandardMeta(
        id="clean-architecture",
        name="Clean Architecture",
        description="Clean Architecture principles",
        weight=1.0,
        source="Robert C. Martin",
        type="custom",
        managed=False,
        origin=None,
        origin_hash=None,
        principle_count=4,
        requirement_count=18,
    )
    assert meta.id == "clean-architecture"
    assert meta.type == "custom"
    assert not meta.managed


def test_standard_reference_creation():
    ref = StandardReference(type="cwe", label="CWE-798", url="https://cwe.mitre.org/data/definitions/798.html")
    assert ref.type == "cwe"
    assert ref.url is not None


def test_standard_reference_no_url():
    ref = StandardReference(type="book", label="Clean Architecture Ch.22", url=None)
    assert ref.url is None


def test_config_paths_has_evaluators_dir(tmp_path):
    cp = ConfigPaths(root=tmp_path / "fake")
    assert cp.evaluators_dir == Path.home() / ".quodeq" / "evaluators"
