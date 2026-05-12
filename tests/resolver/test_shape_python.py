from quodeq.resolver.languages.python import PythonAdapter
from quodeq.resolver.shape import enclosing_function, find_or_seam


def test_enclosing_function_at_line_inside_def():
    adapter = PythonAdapter()
    src = b'''def outer():
    from foo import bar
    return bar()
'''
    fn = enclosing_function(adapter, src, line=2)
    assert fn is not None
    assert fn.name == "outer"
    assert fn.line == 1
    assert fn.lazy_imports_inside_body is True


def test_enclosing_function_at_module_scope_returns_none():
    adapter = PythonAdapter()
    src = b'''
class Foo:
    pass

x = 1
'''
    fn = enclosing_function(adapter, src, line=5)
    assert fn is None


def test_find_or_seam_returns_line_and_pattern():
    adapter = PythonAdapter()
    src = b'''def create_app(provider=None):
    provider = provider or _default_provider()
    return provider
'''
    seam = find_or_seam(adapter, src, function_name="create_app")
    assert seam is not None
    line, pattern = seam
    assert line == 2
    assert "provider or _default_provider()" in pattern


def test_enclosing_function_populates_parameter_names():
    adapter = PythonAdapter()
    src = b'''def create_app(provider, static_dist=None, *, api_key=None):
    return provider
'''
    fn = enclosing_function(adapter, src, line=2)
    assert fn is not None
    assert fn.parameters == ["provider", "static_dist", "api_key"]


def test_enclosing_function_typed_parameters():
    adapter = PythonAdapter()
    src = b'''def create_app(provider: ActionProvider | None = None, port: int = 8080):
    return provider
'''
    fn = enclosing_function(adapter, src, line=2)
    assert fn is not None
    assert fn.parameters == ["provider", "port"]


def test_enclosing_function_args_kwargs():
    adapter = PythonAdapter()
    src = b'''def fn(*args, **kwargs):
    return args, kwargs
'''
    fn = enclosing_function(adapter, src, line=2)
    assert fn is not None
    assert fn.parameters == ["args", "kwargs"]
