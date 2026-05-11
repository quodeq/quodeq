"""Python language adapter for the resolver."""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Language, Node, Parser, Query
from tree_sitter_language_pack import get_language

from quodeq.resolver.languages.base import (
    CallSite,
    ClassDef,
    FunctionDef,
    ImportRecord,
    LanguageAdapter,
    ParamRecord,
    ParseResult,
)

_QUERIES_DIR = Path(__file__).parent / "queries" / "python"


def _load_query(language: Language, name: str) -> Query:
    path = _QUERIES_DIR / name
    text = path.read_text(encoding="utf-8")
    return language.query(text)


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class PythonAdapter(LanguageAdapter):
    language = "python"
    extensions = (".py",)

    def __init__(self) -> None:
        self._language = get_language("python")
        self._parser = Parser(self._language)
        self._q_classes = _load_query(self._language, "class_definitions.scm")

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        root = tree.root_node

        classes = self._extract_classes(root, source)

        return ParseResult(
            classes=classes,
            functions=[],
            params=[],
            imports=[],
            calls=[],
        )

    def _extract_classes(self, root: Node, source: bytes) -> list[ClassDef]:
        out: list[ClassDef] = []
        captures = self._q_classes.captures(root)

        # captures dict: {capture_name: [list of nodes]}
        defs = captures.get("class.def", [])
        names = {n.start_byte: n for n in captures.get("class.name", [])}
        base_lists = {n.start_byte: n for n in captures.get("class.bases", [])}

        for class_node in defs:
            name_node = self._find_child_capture(class_node, names)
            base_node = self._find_child_capture(class_node, base_lists)
            if name_node is None:
                continue
            name = _text(name_node, source)
            bases = self._extract_bases(base_node, source) if base_node else []
            out.append(
                ClassDef(name=name, line=class_node.start_point[0] + 1, bases=bases)
            )
        return out

    @staticmethod
    def _find_child_capture(
        parent: Node, candidates: dict[int, Node]
    ) -> Node | None:
        for offset in range(parent.start_byte, parent.end_byte):
            if offset in candidates:
                node = candidates[offset]
                if node.parent is not None and node.parent.id == parent.id:
                    return node
        return None

    @staticmethod
    def _extract_bases(arg_list: Node, source: bytes) -> list[str]:
        """Extract identifier names from the superclass argument_list."""
        bases: list[str] = []
        for child in arg_list.children:
            if child.type == "identifier":
                bases.append(_text(child, source))
            elif child.type == "attribute":
                # e.g. typing.Protocol - keep the rightmost identifier
                ident = _last_identifier(child, source)
                if ident:
                    bases.append(ident)
        return bases


def _last_identifier(node: Node, source: bytes) -> str | None:
    last: str | None = None
    for child in node.children:
        if child.type == "identifier":
            last = _text(child, source)
    return last
