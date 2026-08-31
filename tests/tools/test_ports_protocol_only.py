"""Guard: services/ports.py stays protocols-only, never regrows concretions.

Concretion defaults belong in services/_wiring.py; ports.py carries only
Protocols and boundary error types imported from quodeq.data.ports.*.
"""
from __future__ import annotations

import ast
from pathlib import Path

_PORTS_PATH = Path(__file__).resolve().parents[2] / "src" / "quodeq" / "services" / "ports.py"

_FORBIDDEN_PREFIXES = (
    "quodeq.data.fs",
    "quodeq.data.sqlite",
    "quodeq.data.actions_log",
    "quodeq.data.migrations",
)


def test_ports_module_imports_no_concretions():
    tree = ast.parse(_PORTS_PATH.read_text(encoding="utf-8"), filename=str(_PORTS_PATH))
    offenders = [
        f"{node.module} (line {node.lineno})"
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith(_FORBIDDEN_PREFIXES)
    ]
    assert offenders == [], (
        "services/ports.py must stay protocols-only — move concretion "
        "re-exports to services/_wiring.py instead:\n" + "\n".join(offenders)
    )
