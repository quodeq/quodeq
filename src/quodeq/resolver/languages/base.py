"""LanguageAdapter abstract base class + parse-result dataclasses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ClassDef:
    name: str
    line: int
    bases: list[str] = field(default_factory=list)


@dataclass
class FunctionDef:
    name: str
    line: int
    signature: str
    return_type: str | None = None


@dataclass
class ParamRecord:
    function_name: str
    function_line: int
    param_name: str
    annotation_text: str | None
    annotation_names: list[str]


@dataclass
class ImportRecord:
    line: int
    imported_name: str
    source_module: str | None
    is_lazy: bool


@dataclass
class CallSite:
    line: int
    callee: str


@dataclass
class ParseResult:
    classes: list[ClassDef]
    functions: list[FunctionDef]
    params: list[ParamRecord]
    imports: list[ImportRecord]
    calls: list[CallSite]


class LanguageAdapter(ABC):
    """Abstract base for per-language parsers/extractors.

    Subclasses must set `language` and `extensions`, and implement `parse`.
    """

    language: str = ""
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, source: bytes) -> ParseResult:
        """Parse a file's bytes into a ParseResult."""
