from pathlib import Path

import pytest

from quodeq.resolver.languages.base import (
    ClassDef,
    FunctionDef,
    ImportRecord,
    LanguageAdapter,
    ParseResult,
)
from quodeq.resolver.registry import (
    LanguageNotSupported,
    get_adapter_for,
    register,
)


class _FakeAdapter(LanguageAdapter):
    language = "fake"
    extensions = (".fake",)

    def parse(self, source: bytes) -> ParseResult:
        return ParseResult(
            classes=[],
            functions=[],
            params=[],
            imports=[],
            calls=[],
        )


def test_register_and_lookup_by_extension(tmp_path: Path):
    register(_FakeAdapter())
    adapter = get_adapter_for(tmp_path / "x.fake")
    assert adapter.language == "fake"


def test_lookup_by_unknown_extension_raises(tmp_path: Path):
    with pytest.raises(LanguageNotSupported):
        get_adapter_for(tmp_path / "x.unknown_ext_xyz")


def test_parse_result_dataclass():
    pr = ParseResult(classes=[], functions=[], params=[], imports=[], calls=[])
    assert pr.classes == []


def test_class_def_dataclass():
    c = ClassDef(name="Foo", line=10, bases=["Bar", "Baz"])
    assert c.name == "Foo"
    assert c.bases == ["Bar", "Baz"]


def test_function_def_dataclass():
    f = FunctionDef(
        name="run",
        line=5,
        signature="def run() -> None",
        return_type="None",
    )
    assert f.return_type == "None"


def test_import_record_dataclass():
    i = ImportRecord(
        line=12,
        imported_name="Foo",
        source_module="bar.baz",
        is_lazy=False,
    )
    assert i.source_module == "bar.baz"
