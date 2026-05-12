from quodeq.resolver.models import (
    FindingInput,
    FunctionInfo,
    Location,
    Manifest,
    ShapePatterns,
)


def test_location_equality():
    a = Location(file="foo/bar.py", line=10)
    b = Location(file="foo/bar.py", line=10)
    assert a == b


def test_location_str():
    loc = Location(file="foo/bar.py", line=10)
    assert str(loc) == "foo/bar.py:10"


def test_function_info_defaults():
    fn = FunctionInfo(
        name="create_app",
        signature="def create_app(provider: ActionProvider | None = None) -> Flask",
        file="app.py",
        line=74,
    )
    assert fn.is_private is False
    assert fn.lazy_imports_inside_body is False


def test_function_info_private_visibility():
    fn = FunctionInfo(
        name="_default_provider",
        signature="def _default_provider() -> ActionProvider",
        file="app.py",
        line=31,
    )
    assert fn.is_private is True


def test_shape_patterns_default_seam_is_none():
    sp = ShapePatterns()
    assert sp.or_seam is None
    assert sp.lazy_imports_inside_body is False


def test_manifest_roundtrip_to_dict():
    m = Manifest(
        target_file="app.py",
        target_line=34,
        target_file_role="composition_root",
        referenced_symbol="FilesystemActionProvider",
    )
    d = m.to_dict()
    assert d["target_file"] == "app.py"
    assert d["target_file_role"] == "composition_root"


def test_finding_input_required_fields():
    f = FindingInput(file="app.py", line=34, category="adaptability")
    assert f.file == "app.py"
    assert f.line == 34
