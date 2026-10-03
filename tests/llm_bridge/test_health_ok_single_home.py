"""The /health body's "ok" status word is declared once in llm_bridge, on
_ollama.py (the module omlx.py and _llamacpp.py both import from already),
not once per bridge."""
from __future__ import annotations

import ast
from pathlib import Path

import quodeq.llm_bridge as llm_bridge

_BRIDGE = Path(llm_bridge.__file__).parent


def _ok_constants(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        target.id
        for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Constant) and node.value.value == "ok"
        for target in node.targets if isinstance(target, ast.Name)
    ]


def test_the_health_ok_word_has_one_home():
    found = {p.name: _ok_constants(p) for p in sorted(_BRIDGE.glob("*.py"))}
    assert {name: names for name, names in found.items() if names} == {"_ollama.py": ["HEALTH_OK"]}
