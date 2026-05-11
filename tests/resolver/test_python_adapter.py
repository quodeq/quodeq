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
