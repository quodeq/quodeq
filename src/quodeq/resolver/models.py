"""Dataclasses used across the resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Location:
    """A file:line reference in the project."""

    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class FunctionInfo:
    """Captured details of a function definition."""

    name: str
    signature: str
    file: str
    line: int
    return_type: str | None = None
    parameters: list[str] = field(default_factory=list)
    lazy_imports_inside_body: bool = False

    @property
    def is_private(self) -> bool:
        return self.name.startswith("_")


@dataclass
class ShapePatterns:
    """Same-file AST shape signals detected near a target line."""

    or_seam: Location | None = None
    or_seam_pattern: str | None = None
    lazy_imports_inside_body: bool = False


@dataclass
class Manifest:
    """Pre-resolved facts the verifier prompt consumes."""

    target_file: str
    target_line: int
    target_file_role: str = "other"
    referenced_symbol: str | None = None
    referenced_symbol_defined_at: Location | None = None
    referenced_symbol_bases: list[str] = field(default_factory=list)
    abstraction: str | None = None
    abstraction_defined_at: Location | None = None
    abstraction_kind: str | None = None
    abstraction_implementations_prod: int = 0
    abstraction_implementations_test_stubs: int = 0
    abstraction_used_as_parameter_type_in: list[Location] = field(default_factory=list)
    target_enclosing_function: FunctionInfo | None = None
    target_parent_function: FunctionInfo | None = None
    target_parent_seam_at: Location | None = None
    target_parent_seam_pattern: str | None = None
    enclosing_function_called_from: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict view for serialization (manifest YAML rendering)."""
        return {
            "target_file": self.target_file,
            "target_line": self.target_line,
            "target_file_role": self.target_file_role,
            "referenced_symbol": self.referenced_symbol,
            "referenced_symbol_defined_at": (
                str(self.referenced_symbol_defined_at)
                if self.referenced_symbol_defined_at
                else None
            ),
            "referenced_symbol_bases": list(self.referenced_symbol_bases),
            "abstraction": self.abstraction,
            "abstraction_defined_at": (
                str(self.abstraction_defined_at) if self.abstraction_defined_at else None
            ),
            "abstraction_kind": self.abstraction_kind,
            "abstraction_implementations_prod": self.abstraction_implementations_prod,
            "abstraction_implementations_test_stubs": self.abstraction_implementations_test_stubs,
            "abstraction_used_as_parameter_type_in": [
                str(loc) for loc in self.abstraction_used_as_parameter_type_in
            ],
            "target_enclosing_function": (
                _function_dict(self.target_enclosing_function)
                if self.target_enclosing_function
                else None
            ),
            "target_parent_function": (
                _function_dict(self.target_parent_function)
                if self.target_parent_function
                else None
            ),
            "target_parent_seam_at": (
                str(self.target_parent_seam_at) if self.target_parent_seam_at else None
            ),
            "target_parent_seam_pattern": self.target_parent_seam_pattern,
            "enclosing_function_called_from": [
                str(loc) for loc in self.enclosing_function_called_from
            ],
        }


def _function_dict(fn: FunctionInfo) -> dict[str, Any]:
    return {
        "name": fn.name,
        "signature": fn.signature,
        "file": fn.file,
        "line": fn.line,
        "return_type": fn.return_type,
        "parameters": list(fn.parameters),
        "lazy_imports_inside_body": fn.lazy_imports_inside_body,
        "is_private": fn.is_private,
    }


@dataclass
class FindingInput:
    """Minimal input a finding must supply to be verifiable."""

    file: str
    line: int
    category: str
    severity: str = "unknown"
    description: str = ""
    cited_text: str = ""
