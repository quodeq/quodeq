# Standards Compiler & Practices Resolver — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build two scripts that merge standards into compiled dimension files and resolve per-language practices with principle assignments and standards refs.

**Architecture:** `compile_standards.py` reads ISO 25010 + CISQ + ASVS, uses `cwe2` for canonical CWE names, outputs `standards/compiled/<dimension>.json`. `resolve_practices.py` reads compiled files + per-language practices (with manually added `principle` field), outputs `practices.resolved.json`. Both are standalone CLI scripts in `tools/`.

**Tech Stack:** Python 3, `cwe2` library, `argparse`, `json`. Tests with `pytest`. Run via `uv run`.

---

### Task 1: Enrich ISO 25010 files with orphan CISQ CWEs

Add the 25 orphan CWEs to the correct ISO 25010 sub-characteristics. Each gets a new
requirement entry with `id`, `text` (from CISQ requirement field), and `cwe` array.

**Files:**
- Modify: `standards/iso25010/maintainability.json`
- Modify: `standards/iso25010/security.json`
- Modify: `standards/iso25010/reliability.json`
- Modify: `standards/iso25010/performance.json`

**Step 1: Add maintainability orphans**

Add to `Modularity.requirements`:
```json
{ "id": "M-MOD-5", "text": "Functions MUST have ≤5 parameters", "cwe": [1064] },
{ "id": "M-MOD-6", "text": "Functions MUST limit outward calls to ≤7 distinct callees to reduce coupling", "cwe": [1048] },
{ "id": "M-MOD-7", "text": "Inheritance depth MUST NOT exceed 4 levels", "cwe": [1074] },
{ "id": "M-MOD-8", "text": "Inheritance hierarchies MUST maintain consistent destructor/cleanup patterns", "cwe": [1045] },
{ "id": "M-MOD-9", "text": "Components MUST call peers or immediate dependencies, not skip layers", "cwe": [1054] },
{ "id": "M-MOD-10", "text": "Trust boundaries MUST be enforced between components of different privilege levels", "cwe": [1090] }
```

Add to `Analyzability.requirements`:
```json
{ "id": "M-ANA-6", "text": "Control flow MUST NOT use unconditional jumps out of deeply nested blocks", "cwe": [1075] },
{ "id": "M-ANA-7", "text": "Loop counter variables MUST NOT be modified inside the loop body", "cwe": [1095] }
```

Add to `Modifiability.requirements`:
```json
{ "id": "M-MDF-5", "text": "Commented-out code MUST be removed; use version control for history", "cwe": [1085] }
```

**Step 2: Add security orphans**

Add to `Confidentiality.requirements`:
```json
{ "id": "S-CON-6", "text": "Passwords MUST NOT appear as literals in source code", "cwe": [259] }
```

Add to `Integrity.requirements`:
```json
{ "id": "S-INT-6", "text": "XML parsers MUST disable external entity resolution", "cwe": [611] }
```

Add to `Authenticity.requirements`:
```json
{ "id": "S-AUT-6", "text": "Server-side HTTP requests MUST validate target URLs against an allowlist", "cwe": [918] }
```

**Step 3: Add reliability orphans**

Add to `Fault Tolerance.requirements`:
```json
{ "id": "R-FT-6", "text": "Return values from fallible operations MUST be checked", "cwe": [252] },
{ "id": "R-FT-7", "text": "Catch blocks MUST target specific exception types, not generic Exception", "cwe": [396] },
{ "id": "R-FT-8", "text": "Throw declarations MUST specify concrete exception types", "cwe": [397] },
{ "id": "R-FT-9", "text": "Boundary and edge-case conditions MUST be checked explicitly", "cwe": [754] },
{ "id": "R-FT-10", "text": "Control flow MUST be structured and predictable; no unreachable statements", "cwe": [691] },
{ "id": "R-FT-11", "text": "Recursive functions MUST have verifiable termination conditions", "cwe": [674] },
{ "id": "R-FT-12", "text": "All loops MUST have reachable termination conditions", "cwe": [835] }
```

**Step 4: Add performance orphans**

Add to `Time Behaviour.requirements`:
```json
{ "id": "P-TIM-7", "text": "String building in loops MUST use builder/join patterns instead of concatenation", "cwe": [1046] },
{ "id": "P-TIM-8", "text": "Queries on large tables MUST use indexes and MUST NOT perform full table scans", "cwe": [1049] },
{ "id": "P-TIM-9", "text": "Repeated lookups MUST use indexed structures (maps, sets) instead of linear search", "cwe": [1067] }
```

Add to `Resource Utilisation.requirements`:
```json
{ "id": "P-RES-6", "text": "Operations MUST NOT allow small inputs to trigger disproportionate resource consumption", "cwe": [405] },
{ "id": "P-RES-7", "text": "Resource allocation MUST be throttled with configurable limits", "cwe": [770] },
{ "id": "P-RES-8", "text": "Resource allocation inside loops MUST be minimised; pre-allocate where possible", "cwe": [1050] }
```

**Step 5: Run existing standards tests**

Run: `uv run pytest tests/v2/test_standards.py -v`
Expected: PASS (structure unchanged, just more entries)

**Step 6: Commit**

```bash
git add standards/iso25010/
git commit -m "feat(standards): enrich ISO 25010 with 25 orphan CISQ CWEs"
```

---

### Task 2: Build `tools/compile_standards.py`

**Files:**
- Create: `tools/compile_standards.py`
- Create: `tests/tools/__init__.py`
- Create: `tests/tools/test_compile_standards.py`
- Output dir: `standards/compiled/`

**Step 1: Write test for CWE index building**

```python
# tests/tools/test_compile_standards.py
import json
from pathlib import Path

# Allow importing from tools/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from compile_standards import build_cwe_index


def test_build_cwe_index_from_iso(tmp_path):
    """CWE index extracts CWEs grouped by principle from ISO 25010."""
    iso_file = tmp_path / "iso25010" / "maintainability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "maintainability",
        "sub_characteristics": [
            {
                "name": "Modularity",
                "requirements": [
                    {"id": "M-MOD-1", "text": "Complexity MUST be ≤10", "cwe": [1121]}
                ]
            }
        ]
    }))
    cisq_file = tmp_path / "cisq" / "maintainability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [
            {"id": 1121, "name": "Excessive Complexity", "requirement": "Complexity MUST be ≤10"}
        ]
    }))

    index = build_cwe_index(tmp_path, "maintainability")
    assert "Modularity" in index
    assert 1121 in index["Modularity"]
    entry = index["Modularity"][1121]
    assert entry["refs"][0]["source"] == "iso25010"
    assert entry["refs"][0]["ref"] == "M-MOD-1"
    assert any(r["source"] == "cisq" for r in entry["refs"])
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_compile_standards.py::test_build_cwe_index_from_iso -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement `build_cwe_index`**

```python
#!/usr/bin/env python3
"""Compile ISO 25010 + CISQ + ASVS standards into merged dimension files.

Usage:
    python3 tools/compile_standards.py [--gaps]
    python3 tools/compile_standards.py --dimension maintainability
"""
import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

STANDARDS_DIR = repo_root / "standards"
OUTPUT_DIR = STANDARDS_DIR / "compiled"

ALL_DIMENSIONS = ["maintainability", "security", "reliability", "performance",
                  "usability", "flexibility"]

# Dimensions that have CISQ backing
CISQ_DIMENSIONS = {"maintainability", "security", "reliability", "performance"}


def _load_cwe_names() -> dict[int, str]:
    """Load canonical CWE names from the cwe2 library."""
    from cwe2.database import Database
    db = Database()
    return db


def _get_cwe_name(db, cwe_id: int) -> str:
    """Get canonical name for a CWE ID, with fallback."""
    try:
        return db.get(cwe_id).name
    except Exception:
        return f"CWE-{cwe_id}"


def build_cwe_index(
    standards_dir: Path,
    dimension: str,
    cwe_db=None,
) -> dict[str, dict[int, dict]]:
    """Build a principle → {cwe_id → {name, refs}} index for a dimension.

    Returns: {"Modularity": {1121: {"name": "...", "refs": [...]}}, ...}
    """
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())

    # Build principle → CWE entries from ISO 25010
    index: dict[str, dict[int, dict]] = {}
    for sc in iso_data.get("sub_characteristics", []):
        principle = sc["name"]
        index[principle] = {}
        for req in sc.get("requirements", []):
            for cwe_id in req.get("cwe", []):
                name = _get_cwe_name(cwe_db, cwe_id) if cwe_db else f"CWE-{cwe_id}"
                if cwe_id not in index[principle]:
                    index[principle][cwe_id] = {"name": name, "refs": []}
                index[principle][cwe_id]["refs"].append({
                    "source": "iso25010",
                    "ref": req["id"],
                    "title": req["text"],
                })

    # Attach CISQ refs
    if dimension in CISQ_DIMENSIONS:
        cisq_file = standards_dir / "cisq" / f"{dimension}.json"
        if cisq_file.exists():
            cisq_data = json.loads(cisq_file.read_text())
            cisq_lookup = {c["id"]: c for c in cisq_data.get("cwes", [])}
            for principle, cwes in index.items():
                for cwe_id, entry in cwes.items():
                    if cwe_id in cisq_lookup:
                        entry["refs"].append({
                            "source": "cisq",
                            "title": cisq_lookup[cwe_id]["requirement"],
                        })

    # Attach ASVS refs (security only, overlap only)
    if dimension == "security":
        asvs_file = standards_dir / "asvs" / "level1.json"
        if asvs_file.exists():
            asvs_data = json.loads(asvs_file.read_text())
            # Build CWE → ASVS requirements lookup
            asvs_by_cwe: dict[int, list[dict]] = {}
            for req in asvs_data.get("requirements", []):
                for cwe_id in req.get("cwe", []):
                    asvs_by_cwe.setdefault(cwe_id, []).append(req)
            for principle, cwes in index.items():
                for cwe_id, entry in cwes.items():
                    if cwe_id in asvs_by_cwe:
                        for asvs_req in asvs_by_cwe[cwe_id]:
                            entry["refs"].append({
                                "source": "asvs",
                                "ref": asvs_req["id"],
                                "section": asvs_req.get("section", ""),
                                "title": asvs_req["text"],
                            })

    return index


def compile_dimension(standards_dir: Path, dimension: str, cwe_db=None) -> dict:
    """Compile a single dimension into the output format."""
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())

    index = build_cwe_index(standards_dir, dimension, cwe_db)

    sources = ["iso25010"]
    if dimension in CISQ_DIMENSIONS:
        sources.append("cisq")
    if dimension == "security":
        sources.append("asvs")

    principles = []
    for principle_name, cwes in index.items():
        cwe_list = []
        for cwe_id, entry in sorted(cwes.items()):
            cwe_list.append({
                "id": cwe_id,
                "name": entry["name"],
                "refs": entry["refs"],
            })
        principles.append({
            "name": principle_name,
            "cwes": cwe_list,
        })

    return {
        "id": dimension,
        "name": iso_data.get("name", dimension.title()),
        "sources": sources,
        "principles": principles,
    }


def report_gaps(standards_dir: Path, dimension: str) -> list[str]:
    """Report CISQ CWEs not found in any ISO 25010 principle."""
    if dimension not in CISQ_DIMENSIONS:
        return []

    # Collect all ISO CWEs
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())
    iso_cwes: set[int] = set()
    for sc in iso_data.get("sub_characteristics", []):
        for req in sc.get("requirements", []):
            iso_cwes.update(req.get("cwe", []))

    # Collect CISQ CWEs
    cisq_file = standards_dir / "cisq" / f"{dimension}.json"
    cisq_data = json.loads(cisq_file.read_text())
    cisq_lookup = {c["id"]: c["name"] for c in cisq_data.get("cwes", [])}

    warnings = []
    for cwe_id, name in sorted(cisq_lookup.items()):
        if cwe_id not in iso_cwes:
            warnings.append(f"orphan: CWE-{cwe_id} ({name}) not in any {dimension} principle")

    return warnings


def main():
    parser = argparse.ArgumentParser(description="Compile standards into merged dimension files")
    parser.add_argument("--dimension", "-d", help="Compile a single dimension")
    parser.add_argument("--gaps", action="store_true", help="Report orphan CWEs only, don't write")
    parser.add_argument("--standards-dir", type=Path, default=STANDARDS_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()

    dimensions = [args.dimension] if args.dimension else ALL_DIMENSIONS
    cwe_db = _load_cwe_names() if not args.gaps else None

    if args.gaps:
        any_gaps = False
        for dim in dimensions:
            warnings = report_gaps(args.standards_dir, dim)
            for w in warnings:
                print(f"  [{dim}] {w}")
                any_gaps = True
        if not any_gaps:
            print("No orphan CWEs found.")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for dim in dimensions:
        compiled = compile_dimension(args.standards_dir, dim, cwe_db)
        out_file = args.output_dir / f"{dim}.json"
        out_file.write_text(json.dumps(compiled, indent=2) + "\n")
        n_principles = len(compiled["principles"])
        n_cwes = sum(len(p["cwes"]) for p in compiled["principles"])
        print(f"  {dim}: {n_principles} principles, {n_cwes} CWEs → {out_file}")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_compile_standards.py::test_build_cwe_index_from_iso -v`
Expected: PASS

**Step 5: Write test for ASVS attachment**

```python
def test_build_cwe_index_attaches_asvs_for_security(tmp_path):
    """ASVS refs are attached to security CWEs that overlap."""
    iso_file = tmp_path / "iso25010" / "security.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "security",
        "sub_characteristics": [{
            "name": "Integrity",
            "requirements": [
                {"id": "S-INT-2", "text": "SQL queries MUST use parameterised statements", "cwe": [89]}
            ]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "security.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [{"id": 89, "name": "SQL Injection", "requirement": "SQL MUST use params"}]
    }))
    asvs_file = tmp_path / "asvs" / "level1.json"
    asvs_file.parent.mkdir(parents=True)
    asvs_file.write_text(json.dumps({
        "requirements": [
            {"id": "V5.3.4", "cwe": [89], "section": "Validation",
             "text": "Verify that database queries use parameterized queries"}
        ]
    }))

    index = build_cwe_index(tmp_path, "security")
    refs = index["Integrity"][89]["refs"]
    sources = [r["source"] for r in refs]
    assert "iso25010" in sources
    assert "cisq" in sources
    assert "asvs" in sources
    asvs_ref = next(r for r in refs if r["source"] == "asvs")
    assert asvs_ref["ref"] == "V5.3.4"
    assert asvs_ref["section"] == "Validation"
```

**Step 6: Run test**

Run: `uv run pytest tests/tools/test_compile_standards.py -v`
Expected: PASS

**Step 7: Write test for gap reporting**

```python
def test_report_gaps_finds_orphan_cwes(tmp_path):
    """Gaps reporter finds CISQ CWEs missing from ISO 25010."""
    iso_file = tmp_path / "iso25010" / "maintainability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "maintainability",
        "sub_characteristics": [{
            "name": "Modularity",
            "requirements": [{"id": "M-MOD-1", "text": "...", "cwe": [1121]}]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "maintainability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [
            {"id": 1121, "name": "Complexity", "requirement": "..."},
            {"id": 9999, "name": "Orphan CWE", "requirement": "..."}
        ]
    }))

    from compile_standards import report_gaps
    gaps = report_gaps(tmp_path, "maintainability")
    assert len(gaps) == 1
    assert "9999" in gaps[0]
    assert "Orphan CWE" in gaps[0]
```

**Step 8: Run test**

Run: `uv run pytest tests/tools/test_compile_standards.py -v`
Expected: PASS

**Step 9: Write test for full compile_dimension output shape**

```python
def test_compile_dimension_output_shape(tmp_path):
    """compile_dimension produces the expected output structure."""
    iso_file = tmp_path / "iso25010" / "reliability.json"
    iso_file.parent.mkdir(parents=True)
    iso_file.write_text(json.dumps({
        "id": "reliability",
        "name": "Reliability",
        "sub_characteristics": [{
            "name": "Fault Tolerance",
            "requirements": [
                {"id": "R-FT-1", "text": "Exceptions MUST be handled", "cwe": [390]}
            ]
        }]
    }))
    cisq_file = tmp_path / "cisq" / "reliability.json"
    cisq_file.parent.mkdir(parents=True)
    cisq_file.write_text(json.dumps({
        "cwes": [{"id": 390, "name": "Error Without Action", "requirement": "Errors MUST trigger handling"}]
    }))

    from compile_standards import compile_dimension
    result = compile_dimension(tmp_path, "reliability")

    assert result["id"] == "reliability"
    assert result["name"] == "Reliability"
    assert "iso25010" in result["sources"]
    assert "cisq" in result["sources"]
    assert len(result["principles"]) == 1
    principle = result["principles"][0]
    assert principle["name"] == "Fault Tolerance"
    assert len(principle["cwes"]) == 1
    cwe = principle["cwes"][0]
    assert cwe["id"] == 390
    assert len(cwe["refs"]) == 2
```

**Step 10: Run all tests**

Run: `uv run pytest tests/tools/test_compile_standards.py -v`
Expected: PASS

**Step 11: Run against real standards data**

Run: `uv run python3 tools/compile_standards.py --gaps`
Expected: No orphan CWEs (after Task 1 enrichment)

Run: `uv run python3 tools/compile_standards.py`
Expected: 6 compiled files written to `standards/compiled/`

**Step 12: Commit**

```bash
git add tools/compile_standards.py tests/tools/ standards/compiled/
git commit -m "feat(tools): add compile_standards.py — merges ISO 25010, CISQ, ASVS"
```

---

### Task 3: Add `principle` field to all practice files

Add `principle` to each practice in all 6 evaluator practice files. The schema also
needs updating. The mapping is based on CWE → ISO 25010 sub-characteristic.

**Files:**
- Modify: `evaluators/python/knowledge/practices.json`
- Modify: `evaluators/typescript/knowledge/practices.json`
- Modify: `evaluators/java/knowledge/practices.json`
- Modify: `evaluators/kotlin/knowledge/practices.json`
- Modify: `evaluators/bash/knowledge/practices.json`
- Modify: `evaluators/mobile_ios/knowledge/practices.json`
- Modify: `src/quodeq/v2/engine/schemas/practices_schema.json`

**Step 1: Update practices_schema.json**

Add `"principle"` to the required array and properties:

```json
"required": ["id", "title", "cwe", "dimension", "principle", "severity", "bad", "good", "explanation"],
"properties": {
  ...
  "principle": { "type": "string", "minLength": 1 },
  ...
}
```

**Step 2: Add principle to Python practices**

All evaluators follow the same CWE→principle pattern. Here's the mapping
(applies to all 6 languages — same CWEs, same principles):

| Practice suffix | CWE | Dimension | Principle |
|--------|------|-----------|-----------|
| -001 | 95 | security | Authenticity |
| -002 | 798 | security | Confidentiality |
| -003 | 78 | security | Authenticity |
| -004 | 89 | security | Integrity |
| -005 | 1080 | maintainability | Analyzability |
| -006 | 1121 | maintainability | Modularity |
| -007 | 1061 | maintainability | Modifiability |
| -008 | 1059 | maintainability | Analyzability |
| -009 | 772 | reliability | Recoverability |
| -010 | 390 | reliability | Fault Tolerance |
| -011 | 476 | reliability | Fault Tolerance |
| -012 | 755 | reliability | Fault Tolerance |
| -013 | 400 | performance | Resource Utilisation |
| -014 | 1084 | performance | Time Behaviour |
| -015 | 1057 | performance | Resource Utilisation |
| -016 | 1084 | performance | Time Behaviour |

Note: TypeScript uses different ID numbering. Check each practice's CWE and map accordingly.

Add `"principle": "<value>"` to each practice object in all 6 files.

**Step 3: Run schema validation test**

Run: `uv run pytest tests/v2/test_schema_validator.py -v`
Expected: PASS

Run: `uv run pytest tests/v2/test_plugin_python.py tests/v2/test_plugin_typescript.py -v`
Expected: PASS (plugins validate their practices against schema)

**Step 4: Commit**

```bash
git add evaluators/*/knowledge/practices.json src/quodeq/v2/engine/schemas/practices_schema.json
git commit -m "feat(evaluators): add principle field to all practices"
```

---

### Task 4: Build `tools/resolve_practices.py`

**Files:**
- Create: `tools/resolve_practices.py`
- Create: `tests/tools/test_resolve_practices.py`

**Step 1: Write test for practice resolution**

```python
# tests/tools/test_resolve_practices.py
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from resolve_practices import resolve_practice


def test_resolve_practice_enriches_cwe_and_standards():
    """resolve_practice replaces bare CWE int with {id, name} and adds standards."""
    compiled = {
        "id": "maintainability",
        "principles": [{
            "name": "Analyzability",
            "cwes": [{
                "id": 1080,
                "name": "Source Code File with Excessive Number of Lines of Code",
                "refs": [
                    {"source": "iso25010", "ref": "M-ANA-1", "title": "Source files MUST NOT exceed 300 lines"},
                    {"source": "cisq", "title": "Source files MUST NOT exceed language-appropriate line limits"}
                ]
            }]
        }]
    }

    practice = {
        "id": "py-005",
        "title": "Keep source files under 300 lines",
        "dimension": "maintainability",
        "principle": "Analyzability",
        "cwe": 1080,
        "severity": "medium",
        "bad": "# 500 lines",
        "good": "# 200 lines",
        "explanation": "Split large files"
    }

    resolved, warnings = resolve_practice(practice, {"maintainability": compiled})

    assert resolved["cwe"] == {"id": 1080, "name": "Source Code File with Excessive Number of Lines of Code"}
    assert len(resolved["standards"]) == 2
    assert resolved["standards"][0]["source"] == "iso25010"
    assert resolved["principle"] == "Analyzability"
    assert resolved["bad"] == "# 500 lines"  # preserved
    assert len(warnings) == 0
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_resolve_practices.py::test_resolve_practice_enriches_cwe_and_standards -v`
Expected: FAIL

**Step 3: Implement resolve_practices.py**

```python
#!/usr/bin/env python3
"""Resolve per-language practices with compiled standards data.

Usage:
    python3 tools/resolve_practices.py --lang python
    python3 tools/resolve_practices.py --all
    python3 tools/resolve_practices.py --validate
"""
import argparse
import json
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
COMPILED_DIR = repo_root / "standards" / "compiled"
EVALUATORS_DIR = repo_root / "evaluators"


def load_compiled_standards(compiled_dir: Path) -> dict[str, dict]:
    """Load all compiled dimension files into a dict keyed by dimension id."""
    standards = {}
    for f in compiled_dir.glob("*.json"):
        data = json.loads(f.read_text())
        standards[data["id"]] = data
    return standards


def resolve_practice(practice: dict, compiled: dict[str, dict]) -> tuple[dict, list[str]]:
    """Resolve a single practice against compiled standards.

    Returns (resolved_practice, warnings).
    """
    warnings: list[str] = []
    resolved = dict(practice)  # shallow copy
    pid = practice["id"]
    dimension = practice.get("dimension", "")
    principle = practice.get("principle", "")
    cwe_id = practice.get("cwe")

    if dimension not in compiled:
        warnings.append(f"{pid}: dimension '{dimension}' not in compiled standards")
        return resolved, warnings

    dim_data = compiled[dimension]

    # Find the CWE in the declared principle
    cwe_entry = None
    found_in_principle = None
    for p in dim_data.get("principles", []):
        for cwe in p.get("cwes", []):
            if cwe["id"] == cwe_id:
                if p["name"] == principle:
                    cwe_entry = cwe
                    found_in_principle = p["name"]
                elif cwe_entry is None:
                    # Found under a different principle
                    cwe_entry = cwe
                    found_in_principle = p["name"]

    if cwe_entry is None:
        warnings.append(f"{pid}: CWE-{cwe_id} not found in compiled {dimension}")
        resolved["cwe"] = {"id": cwe_id, "name": f"CWE-{cwe_id}"}
        resolved["standards"] = []
        return resolved, warnings

    if found_in_principle != principle:
        warnings.append(
            f"{pid}: declares principle '{principle}' but CWE-{cwe_id} "
            f"found under '{found_in_principle}'"
        )

    resolved["cwe"] = {"id": cwe_entry["id"], "name": cwe_entry["name"]}
    resolved["standards"] = cwe_entry["refs"]

    return resolved, warnings


def resolve_evaluator(lang_dir: Path, compiled: dict[str, dict], validate_only: bool = False) -> tuple[dict | None, list[str]]:
    """Resolve all practices for one evaluator.

    Returns (resolved_data, all_warnings). resolved_data is None in validate mode.
    """
    practices_file = lang_dir / "knowledge" / "practices.json"
    if not practices_file.exists():
        return None, [f"{lang_dir.name}: no practices.json"]

    data = json.loads(practices_file.read_text())
    all_warnings: list[str] = []
    resolved_practices = []

    for practice in data.get("practices", []):
        resolved, warnings = resolve_practice(practice, compiled)
        resolved_practices.append(resolved)
        all_warnings.extend(warnings)

    if validate_only:
        return None, all_warnings

    resolved_data = dict(data)
    resolved_data["practices"] = resolved_practices
    return resolved_data, all_warnings


def main():
    parser = argparse.ArgumentParser(description="Resolve practices with compiled standards")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--lang", "-l", help="Resolve one language (e.g. python)")
    group.add_argument("--all", "-a", action="store_true", help="Resolve all evaluators")
    group.add_argument("--validate", "-v", action="store_true", help="Validate only, don't write")
    parser.add_argument("--compiled-dir", type=Path, default=COMPILED_DIR)
    parser.add_argument("--evaluators-dir", type=Path, default=EVALUATORS_DIR)
    args = parser.parse_args()

    compiled = load_compiled_standards(args.compiled_dir)
    if not compiled:
        print(f"Error: no compiled standards in {args.compiled_dir}", file=sys.stderr)
        sys.exit(1)

    if args.validate:
        langs = sorted(d.name for d in args.evaluators_dir.iterdir()
                       if d.is_dir() and not d.name.startswith("_"))
    elif args.all:
        langs = sorted(d.name for d in args.evaluators_dir.iterdir()
                       if d.is_dir() and not d.name.startswith("_"))
    else:
        langs = [args.lang]

    any_warnings = False
    for lang in langs:
        lang_dir = args.evaluators_dir / lang
        resolved_data, warnings = resolve_evaluator(
            lang_dir, compiled, validate_only=args.validate
        )

        for w in warnings:
            print(f"  WARNING: {w}", file=sys.stderr)
            any_warnings = True

        if resolved_data is not None:
            out_file = lang_dir / "knowledge" / "practices.resolved.json"
            out_file.write_text(json.dumps(resolved_data, indent=2) + "\n")
            n = len(resolved_data.get("practices", []))
            print(f"  {lang}: {n} practices → {out_file}")

    if args.validate:
        if any_warnings:
            print("Validation found warnings.", file=sys.stderr)
            sys.exit(1)
        else:
            print("All practices valid.")


if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/tools/test_resolve_practices.py -v`
Expected: PASS

**Step 5: Write test for warning on mismatched principle**

```python
def test_resolve_practice_warns_on_principle_mismatch():
    """Warning when practice declares principle X but CWE is under principle Y."""
    compiled = {
        "maintainability": {
            "id": "maintainability",
            "principles": [{
                "name": "Modularity",
                "cwes": [{"id": 1080, "name": "Excessive Lines", "refs": []}]
            }]
        }
    }

    practice = {
        "id": "py-005", "title": "...", "dimension": "maintainability",
        "principle": "Analyzability",  # wrong — CWE is under Modularity
        "cwe": 1080, "severity": "medium", "bad": "", "good": "", "explanation": ""
    }

    _, warnings = resolve_practice(practice, compiled)
    assert len(warnings) == 1
    assert "Analyzability" in warnings[0]
    assert "Modularity" in warnings[0]
```

**Step 6: Write test for missing CWE warning**

```python
def test_resolve_practice_warns_on_missing_cwe():
    """Warning when practice CWE is not in any compiled standard."""
    compiled = {
        "security": {
            "id": "security",
            "principles": [{"name": "Integrity", "cwes": []}]
        }
    }

    practice = {
        "id": "py-099", "title": "...", "dimension": "security",
        "principle": "Integrity", "cwe": 9999,
        "severity": "medium", "bad": "", "good": "", "explanation": ""
    }

    resolved, warnings = resolve_practice(practice, compiled)
    assert len(warnings) == 1
    assert "9999" in warnings[0]
    assert resolved["cwe"] == {"id": 9999, "name": "CWE-9999"}
    assert resolved["standards"] == []
```

**Step 7: Run all tests**

Run: `uv run pytest tests/tools/ -v`
Expected: PASS

**Step 8: Run against real data**

Run: `uv run python3 tools/resolve_practices.py --all`
Expected: 6 resolved files, no warnings

**Step 9: Commit**

```bash
git add tools/resolve_practices.py tests/tools/test_resolve_practices.py evaluators/*/knowledge/practices.resolved.json
git commit -m "feat(tools): add resolve_practices.py — enriches practices with standards refs"
```

---

### Task 5: Verify end-to-end and clean up

**Files:**
- Verify: `standards/compiled/*.json` (6 files)
- Verify: `evaluators/*/knowledge/practices.resolved.json` (6 files)

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: All pass

**Step 2: Spot-check compiled output**

Run: `uv run python3 -c "import json; d=json.loads(open('standards/compiled/maintainability.json').read()); print(json.dumps(d['principles'][0], indent=2))" | head -20`
Expected: Modularity principle with CWEs and refs

**Step 3: Spot-check resolved output**

Run: `uv run python3 -c "import json; d=json.loads(open('evaluators/python/knowledge/practices.resolved.json').read()); print(json.dumps(d['practices'][0], indent=2))"`
Expected: Practice with enriched CWE object and standards array

**Step 4: Verify gap report is clean**

Run: `uv run python3 tools/compile_standards.py --gaps`
Expected: "No orphan CWEs found."

**Step 5: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: verify standards compiler end-to-end"
```
