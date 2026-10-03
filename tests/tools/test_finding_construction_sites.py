"""Guard: findings are built and emitted only where admission has placed them.

A finding's principle, requirement and dimension come from its standard,
derived in one place (``quodeq.core.admission``). Every site that builds a
``Judgment`` or emits a ``JudgmentCreatedEvent`` is listed here with the
admission step it sits behind. A new site fails this test: route it through
``admit`` (writers), ``PrincipleResolver.place`` (readers), or the
projection's admitter, then add it here with that reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src" / "quodeq"

_ALLOWED: dict[str, dict[str, str]] = {
    "Judgment": {
        "core/finding_mappings.py": "lifts a wire row the enricher or replay already admitted",
        "core/evidence/jsonl.py": "reader: parsed rows are placed by PrincipleResolver.place",
        "core/checks/_judgments.py": "checker output, admitted by analysis/checks/admission.py",
    },
    "JudgmentCreatedEvent": {
        "analysis/mcp/router.py": "emits enricher-admitted findings; unmapped ones never",
        "analysis/cache/_replay.py": "emits findings readmit placed; unmapped ones never",
        "analysis/checks/runner.py": "emits only the judgments admit_all kept",
    },
}


def _construction_sites() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {name: set() for name in _ALLOWED}
    for path in sorted(_SRC.rglob("*.py")):
        rel = path.relative_to(_SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name in found:
                    found[name].add(rel)
    return found


def test_findings_are_only_built_behind_admission():
    found = _construction_sites()
    unexpected = {
        name: sorted(sites - set(_ALLOWED[name])) for name, sites in found.items()
        if sites - set(_ALLOWED[name])
    }
    assert not unexpected, (
        "New finding construction outside admission. Place it through "
        "quodeq.core.admission first, then list the site here with the reason:\n"
        + "\n".join(f"  {name}: {sites}" for name, sites in unexpected.items())
    )


def test_the_allowlist_has_no_stale_entries():
    found = _construction_sites()
    stale = {name: sorted(set(_ALLOWED[name]) - sites) for name, sites in found.items()
             if set(_ALLOWED[name]) - sites}
    assert not stale, f"Remove allowlist entries that no longer build findings: {stale}"
