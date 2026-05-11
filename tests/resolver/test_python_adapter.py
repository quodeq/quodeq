from quodeq.resolver.languages.python import PythonAdapter


def test_extracts_simple_class_with_base():
    adapter = PythonAdapter()
    src = b'''
class Foo(Bar):
    pass
'''
    result = adapter.parse(src)
    assert len(result.classes) == 1
    c = result.classes[0]
    assert c.name == "Foo"
    assert c.line == 2
    assert c.bases == ["Bar"]


def test_extracts_class_with_multiple_bases():
    adapter = PythonAdapter()
    src = b'''
class FilesystemActionProvider(FsEvaluationMixin, FsToolingMixin, ActionProvider):
    """docstring"""
    pass
'''
    result = adapter.parse(src)
    assert len(result.classes) == 1
    c = result.classes[0]
    assert c.name == "FilesystemActionProvider"
    assert c.bases == ["FsEvaluationMixin", "FsToolingMixin", "ActionProvider"]


def test_extracts_protocol_class():
    adapter = PythonAdapter()
    src = b'''
from typing import Protocol


class ActionProvider(ProjectActions, ReportActions, Protocol):
    """top-level protocol"""
    ...
'''
    result = adapter.parse(src)
    assert len(result.classes) == 1
    assert result.classes[0].bases == ["ProjectActions", "ReportActions", "Protocol"]


def test_no_classes_in_empty_file():
    adapter = PythonAdapter()
    result = adapter.parse(b"")
    assert result.classes == []


def test_nested_classes_with_independent_bases():
    adapter = PythonAdapter()
    src = b'''
class Outer:
    class Inner(BaseInner):
        pass
'''
    result = adapter.parse(src)
    classes_by_name = {c.name: c for c in result.classes}
    assert "Outer" in classes_by_name
    assert "Inner" in classes_by_name
    # Outer has no bases (the parentheses are absent in `class Outer:`)
    assert classes_by_name["Outer"].bases == []
    # Inner has exactly its own base
    assert classes_by_name["Inner"].bases == ["BaseInner"]


def test_outer_with_bases_and_nested_class_with_different_bases():
    adapter = PythonAdapter()
    src = b'''
class Outer(BaseOuter):
    class Inner(BaseInner):
        pass
'''
    result = adapter.parse(src)
    classes_by_name = {c.name: c for c in result.classes}
    assert classes_by_name["Outer"].bases == ["BaseOuter"]
    assert classes_by_name["Inner"].bases == ["BaseInner"]
