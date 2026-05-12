"""Same-file AST shape detectors built on a LanguageAdapter."""

from __future__ import annotations

from tree_sitter import Node

from quodeq.resolver.languages.python import PythonAdapter, _load_query, _text, _walk
from quodeq.resolver.models import FunctionInfo


def enclosing_function(
    adapter: PythonAdapter, source: bytes, line: int
) -> FunctionInfo | None:
    """Return the innermost function whose body contains `line`, or None."""
    tree = adapter._parser.parse(source)
    target_line = line - 1  # tree-sitter is 0-indexed
    best: Node | None = None
    for fn_node in _walk(tree.root_node, "function_definition"):
        body = fn_node.child_by_field_name("body")
        if body is None:
            continue
        if body.start_point[0] <= target_line <= body.end_point[0]:
            best = fn_node if best is None else _smaller(best, fn_node)
    if best is None:
        return None
    name_node = best.child_by_field_name("name")
    ret_node = best.child_by_field_name("return_type")
    body = best.child_by_field_name("body")
    params_node = best.child_by_field_name("parameters")
    name = _text(name_node, source) if name_node else "<anon>"
    signature = source[best.start_byte:(body.start_byte if body else best.end_byte)].decode("utf-8", errors="replace").strip().rstrip(":").strip()
    return FunctionInfo(
        name=name,
        signature=signature,
        file="",
        line=best.start_point[0] + 1,
        return_type=_text(ret_node, source) if ret_node else None,
        parameters=_extract_param_names(params_node, source),
        lazy_imports_inside_body=_has_lazy_imports(best),
    )


def find_or_seam(
    adapter: PythonAdapter, source: bytes, function_name: str
) -> tuple[int, str] | None:
    """Find the first `param = param or factory()` line inside the named function."""
    tree = adapter._parser.parse(source)
    query = _load_query(adapter._language, "shape_or_seam.scm")
    for fn_node in _walk(tree.root_node, "function_definition"):
        name_node = fn_node.child_by_field_name("name")
        if name_node is None or _text(name_node, source) != function_name:
            continue
        body = fn_node.child_by_field_name("body")
        if body is None:
            continue
        for capture_name, nodes in query.captures(body).items():
            if capture_name != "seam.assignment":
                continue
            for assign in nodes:
                # confirm lhs name == left operand of `or`
                lhs = assign.child_by_field_name("left")
                rhs = assign.child_by_field_name("right")
                if lhs is None or rhs is None:
                    continue
                rhs_left = rhs.child_by_field_name("left")
                if rhs_left is None:
                    continue
                if _text(lhs, source) != _text(rhs_left, source):
                    continue
                line = assign.start_point[0] + 1
                pattern = _text(assign, source)
                return line, pattern
    return None


def _smaller(a: Node, b: Node) -> Node:
    a_size = a.end_byte - a.start_byte
    b_size = b.end_byte - b.start_byte
    return a if a_size <= b_size else b


def _has_lazy_imports(fn_node: Node) -> bool:
    body = fn_node.child_by_field_name("body")
    if body is None:
        return False
    for child in _walk(body, "import_from_statement"):
        return True
    for child in _walk(body, "import_statement"):
        return True
    return False


def _extract_param_names(params_node: Node | None, source: bytes) -> list[str]:
    """Extract parameter names from a `parameters` node.

    Handles all Python parameter forms: bare identifiers (`x`),
    typed parameters (`x: int`), default parameters (`x=5`),
    typed default parameters (`x: int = 5`), and *args/**kwargs.
    Skips `self`, `cls`, `/`, `*` markers.
    """
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        if child.type == "identifier":
            text = _text(child, source)
            names.append(text)
        elif child.type in ("typed_parameter", "default_parameter", "typed_default_parameter"):
            # typed_parameter: first child is the identifier
            # default_parameter & typed_default_parameter: name field
            name_node = child.child_by_field_name("name")
            if name_node is None:
                # typed_parameter doesn't have a `name:` field; find first identifier child
                for grand in child.children:
                    if grand.type == "identifier":
                        name_node = grand
                        break
            if name_node is not None:
                names.append(_text(name_node, source))
        elif child.type == "list_splat_pattern":
            # *args
            for grand in child.children:
                if grand.type == "identifier":
                    names.append(_text(grand, source))
        elif child.type == "dictionary_splat_pattern":
            # **kwargs
            for grand in child.children:
                if grand.type == "identifier":
                    names.append(_text(grand, source))
    return names
