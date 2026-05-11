"""Language adapters. Importing this package self-registers each adapter."""

from quodeq.resolver.languages._stub import StubAdapter
from quodeq.resolver.languages.python import PythonAdapter
from quodeq.resolver.registry import register

register(PythonAdapter())
register(StubAdapter())
