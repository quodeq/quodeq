from __future__ import annotations

import ast
from pathlib import Path


def test_no_direct_stderr_prints_in_pipeline() -> None:
    """The CLI pipeline must route progress messages through log_info, not print(..., file=sys.stderr).

    Allowed exceptions: dimension score lines in _execute_pipeline's success branch
    (line 133: `print(f"  {dim}: {score}")`) because those print to stdout for
    shell piping.
    """
    src = Path("src/quodeq/_cli_evaluation.py").read_text()
    tree = ast.parse(src)
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            for kw in node.keywords:
                if kw.arg == "file" and isinstance(kw.value, ast.Attribute) and kw.value.attr == "stderr":
                    offenders.append((node.lineno, ast.unparse(node)))
    assert not offenders, f"direct stderr prints remain: {offenders}"
