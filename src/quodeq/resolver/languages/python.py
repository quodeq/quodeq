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
        self._q_functions = _load_query(self._language, "function_definitions.scm")
        self._q_params = _load_query(self._language, "parameter_annotations.scm")
        self._q_imports = _load_query(self._language, "imports.scm")

    def parse(self, source: bytes) -> ParseResult:
        tree = self._parser.parse(source)
        root = tree.root_node

        classes = self._extract_classes(root, source)
        functions, params = self._extract_functions(root, source)
        imports = self._extract_imports(root, source)

        return ParseResult(
            classes=classes,
            functions=functions,
            params=params,
            imports=imports,
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

    def _extract_functions(
        self, root: Node, source: bytes
    ) -> tuple[list[FunctionDef], list[ParamRecord]]:
        functions: list[FunctionDef] = []
        params: list[ParamRecord] = []

        for fn_node in _walk(root, "function_definition"):
            name_node = fn_node.child_by_field_name("name")
            params_node = fn_node.child_by_field_name("parameters")
            ret_node = fn_node.child_by_field_name("return_type")
            if name_node is None or params_node is None:
                continue
            name = _text(name_node, source)
            line = fn_node.start_point[0] + 1
            signature = self._signature_text(fn_node, source)
            return_type = _text(ret_node, source) if ret_node else None
            functions.append(
                FunctionDef(
                    name=name, line=line, signature=signature, return_type=return_type
                )
            )

            # parameters with annotations
            for capture_name, nodes in self._q_params.captures(params_node).items():
                if capture_name != "param":
                    continue
                for param_node in nodes:
                    pname_node = param_node.child_by_field_name(
                        "name"
                    ) or _first_named_child(param_node, "identifier")
                    type_node = param_node.child_by_field_name("type")
                    if pname_node is None or type_node is None:
                        continue
                    annot_text = _text(type_node, source)
                    annot_names = _identifier_names(type_node, source)
                    params.append(
                        ParamRecord(
                            function_name=name,
                            function_line=line,
                            param_name=_text(pname_node, source),
                            annotation_text=annot_text,
                            annotation_names=annot_names,
                        )
                    )

        return functions, params

    def _extract_imports(self, root: Node, source: bytes) -> list[ImportRecord]:
        out: list[ImportRecord] = []
        for stmt in _walk(root, "import_from_statement"):
            module_node = stmt.child_by_field_name("module_name")
            module = _text(module_node, source) if module_node else None
            is_lazy = _is_inside_function(stmt)
            # Each "name:" field can be a dotted_name or aliased_import
            for child in stmt.children_by_field_name("name"):
                if child.type == "dotted_name":
                    name = _text(child, source).split(".")[-1]
                    out.append(
                        ImportRecord(
                            line=stmt.start_point[0] + 1,
                            imported_name=name,
                            source_module=module,
                            is_lazy=is_lazy,
                        )
                    )
                elif child.type == "aliased_import":
                    alias_node = child.child_by_field_name("alias")
                    if alias_node:
                        out.append(
                            ImportRecord(
                                line=stmt.start_point[0] + 1,
                                imported_name=_text(alias_node, source),
                                source_module=module,
                                is_lazy=is_lazy,
                            )
                        )
        for stmt in _walk(root, "import_statement"):
            for name_node in stmt.children_by_field_name("name"):
                if name_node.type == "dotted_name":
                    out.append(
                        ImportRecord(
                            line=stmt.start_point[0] + 1,
                            imported_name=_text(name_node, source).split(".")[-1],
                            source_module=None,
                            is_lazy=_is_inside_function(stmt),
                        )
                    )
                elif name_node.type == "aliased_import":
                    alias_node = name_node.child_by_field_name("alias")
                    if alias_node:
                        out.append(
                            ImportRecord(
                                line=stmt.start_point[0] + 1,
                                imported_name=_text(alias_node, source),
                                source_module=None,
                                is_lazy=_is_inside_function(stmt),
                            )
                        )
        return out

    @staticmethod
    def _signature_text(fn_node: Node, source: bytes) -> str:
        """Return the function header text (up to and including the return type)."""
        body = fn_node.child_by_field_name("body")
        end = body.start_byte if body else fn_node.end_byte
        return source[fn_node.start_byte:end].decode("utf-8", errors="replace").strip().rstrip(":").strip()


def _last_identifier(node: Node, source: bytes) -> str | None:
    last: str | None = None
    for child in node.children:
        if child.type == "identifier":
            last = _text(child, source)
    return last


def _walk(node: Node, node_type: str):
    """Yield all descendants (and self) matching node_type."""
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from _walk(child, node_type)


def _first_named_child(node: Node, type_name: str) -> Node | None:
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _identifier_names(node: Node, source: bytes) -> list[str]:
    out: list[str] = []
    if node.type == "identifier":
        out.append(_text(node, source))
    for child in node.children:
        out.extend(_identifier_names(child, source))
    return out


def _is_inside_function(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.type == "function_definition":
            return True
        parent = parent.parent
    return False
