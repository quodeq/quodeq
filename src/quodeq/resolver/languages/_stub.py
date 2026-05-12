"""Stub adapter used only to validate that the registry pattern supports
multi-language extensibility. Future language adapters follow the same shape:
declare extensions, implement parse(), and self-register from __init__.py.
"""

from __future__ import annotations

from quodeq.resolver.languages.base import LanguageAdapter, ParseResult


class StubAdapter(LanguageAdapter):
    language = "stub"
    extensions = (".stub",)

    def parse(self, source: bytes) -> ParseResult:
        return ParseResult(classes=[], functions=[], params=[], imports=[], calls=[])
