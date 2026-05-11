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


def test_extracts_function_with_signature():
    adapter = PythonAdapter()
    src = b'''
def _default_provider() -> ActionProvider:
    """docstring"""
    return FilesystemActionProvider()
'''
    result = adapter.parse(src)
    assert len(result.functions) == 1
    fn = result.functions[0]
    assert fn.name == "_default_provider"
    assert fn.line == 2
    assert "ActionProvider" in fn.signature
    assert fn.return_type == "ActionProvider"


def test_extracts_function_with_annotated_parameter():
    adapter = PythonAdapter()
    src = b'''
def create_app(provider: ActionProvider | None = None) -> Flask:
    pass
'''
    result = adapter.parse(src)
    assert len(result.functions) == 1
    assert len(result.params) == 1
    p = result.params[0]
    assert p.function_name == "create_app"
    assert p.param_name == "provider"
    assert "ActionProvider" in p.annotation_names


def test_param_without_annotation_omitted():
    adapter = PythonAdapter()
    src = b'''
def f(x):
    pass
'''
    result = adapter.parse(src)
    assert result.params == []


def test_extracts_top_level_import():
    adapter = PythonAdapter()
    src = b'''
from quodeq.services.base import ActionProvider
'''
    result = adapter.parse(src)
    assert len(result.imports) == 1
    i = result.imports[0]
    assert i.imported_name == "ActionProvider"
    assert i.source_module == "quodeq.services.base"
    assert i.is_lazy is False


def test_marks_lazy_import_inside_function():
    adapter = PythonAdapter()
    src = b'''
def _default_provider():
    from quodeq.services.filesystem import FilesystemActionProvider
    return FilesystemActionProvider()
'''
    result = adapter.parse(src)
    assert len(result.imports) == 1
    assert result.imports[0].imported_name == "FilesystemActionProvider"
    assert result.imports[0].is_lazy is True


def test_extracts_plain_aliased_import():
    adapter = PythonAdapter()
    src = b'''
import sys as system_lib
'''
    result = adapter.parse(src)
    assert len(result.imports) == 1
    i = result.imports[0]
    assert i.imported_name == "system_lib"
    assert i.source_module is None
    assert i.is_lazy is False


def test_extracts_dotted_plain_aliased_import():
    adapter = PythonAdapter()
    src = b'''
import os.path as path_lib
'''
    result = adapter.parse(src)
    assert len(result.imports) == 1
    i = result.imports[0]
    assert i.imported_name == "path_lib"
    assert i.source_module is None
    assert i.is_lazy is False


def test_extracts_call_sites_with_callee_names():
    adapter = PythonAdapter()
    src = b'''
def create_app(provider=None):
    provider = provider or _default_provider()
    helper(arg)
'''
    result = adapter.parse(src)
    callees = sorted(c.callee for c in result.calls)
    assert "_default_provider" in callees
    assert "helper" in callees
