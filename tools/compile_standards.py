#!/usr/bin/env python3
"""Compile ISO 25010 + CISQ + ASVS + CERT + WCAG standards into merged dimension files.

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

CISQ_DIMENSIONS = {"maintainability", "security", "reliability", "performance"}
WCAG_DIMENSIONS = {"usability"}
CERT_DIMENSIONS = {"reliability"}

_ASVS_MAIN_URL = "https://owasp.org/www-project-application-security-verification-standard/"
_CISQ_MAIN_URL = "https://www.it-cisq.org/coding-rules/"
_CERT_MAIN_URL = "https://wiki.sei.cmu.edu/confluence/display/seccode"


def _load_cwe_names() -> object:
    """Load canonical CWE names from the cwe2 library."""
    from cwe2.database import Database
    return Database()


def _get_cwe_name(db, cwe_id: int) -> str:
    """Get canonical name for a CWE ID, with fallback."""
    try:
        return db.get(cwe_id).name
    except (AttributeError, KeyError):
        return f"CWE-{cwe_id}"


def _build_req_index(iso_data: dict) -> dict[str, list[dict]]:
    """Build principle -> [requirement] index from ISO 25010 data.

    Each requirement dict has:
      id, source, text, severity, scope, refs (empty list),
      _cwe_ids, _wcag_ids, _cert_ids (internal, stripped before output)
    """
    index: dict[str, list[dict]] = {}
    for sc in iso_data.get("sub_characteristics", []):
        principle = sc["name"]
        index[principle] = []
        for req in sc.get("requirements", []):
            index[principle].append({
                "id": req["id"],
                "source": "iso25010",
                "text": req["text"],
                "severity": req.get("severity"),
                "scope": req.get("scope"),
                "_cwe_ids": req.get("cwe", []),
                "_wcag_ids": req.get("wcag", []),
                "_cert_ids": req.get("cert", []),
                "refs": [],
            })
    return index


def _attach_cwe_refs(index: dict[str, list[dict]], cwe_db: object | None) -> None:
    """Add a CWE ref for each CWE ID referenced by a requirement."""
    for reqs in index.values():
        for req in reqs:
            for cwe_id in req["_cwe_ids"]:
                name = _get_cwe_name(cwe_db, cwe_id) if cwe_db else f"CWE-{cwe_id}"
                req["refs"].append({
                    "source": "cwe",
                    "id": str(cwe_id),
                    "name": name,
                    "url": f"https://cwe.mitre.org/data/definitions/{cwe_id}.html",
                })


def _attach_cisq_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach CISQ cross-references to requirements whose CWEs appear in CISQ."""
    if dimension not in CISQ_DIMENSIONS:
        return
    cisq_file = standards_dir / "cisq" / f"{dimension}.json"
    if not cisq_file.exists():
        return
    cisq_data = json.loads(cisq_file.read_text())
    cisq_lookup = {c["id"]: c for c in cisq_data.get("cwes", [])}
    for reqs in index.values():
        for req in reqs:
            seen: set[int] = set()
            for cwe_id in req["_cwe_ids"]:
                if cwe_id in cisq_lookup and cwe_id not in seen:
                    seen.add(cwe_id)
                    req["refs"].append({
                        "source": "cisq",
                        "id": None,
                        "name": cisq_lookup[cwe_id]["requirement"],
                        "url": _CISQ_MAIN_URL,
                    })


def _attach_asvs_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach ASVS cross-references (security dimension only)."""
    if dimension != "security":
        return
    asvs_file = standards_dir / "asvs" / "level1.json"
    if not asvs_file.exists():
        return
    asvs_data = json.loads(asvs_file.read_text())
    asvs_by_cwe: dict[int, list[dict]] = {}
    for r in asvs_data.get("requirements", []):
        for cwe_id in r.get("cwe", []):
            asvs_by_cwe.setdefault(cwe_id, []).append(r)
    for reqs in index.values():
        for req in reqs:
            seen: set[str] = set()
            for cwe_id in req["_cwe_ids"]:
                for asvs_req in asvs_by_cwe.get(cwe_id, []):
                    asvs_id = asvs_req["id"]
                    if asvs_id not in seen:
                        seen.add(asvs_id)
                        req["refs"].append({
                            "source": "asvs",
                            "id": asvs_id,
                            "name": asvs_req["text"],
                            "url": _ASVS_MAIN_URL,
                        })


def _attach_cert_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach CERT cross-references via CWE matching and explicit cert fields."""
    if dimension not in CERT_DIMENSIONS:
        return
    cert_file = standards_dir / "cert" / f"{dimension}.json"
    if not cert_file.exists():
        return
    cert_data = json.loads(cert_file.read_text())
    cert_by_cwe: dict[int, list[dict]] = {}
    cert_by_id: dict[str, dict] = {}
    for rule in cert_data.get("rules", []):
        cert_by_id[rule["id"]] = rule
        for cwe_id in rule.get("cwe", []):
            cert_by_cwe.setdefault(cwe_id, []).append(rule)
    for reqs in index.values():
        for req in reqs:
            seen: set[str] = set()
            for cwe_id in req["_cwe_ids"]:
                for rule in cert_by_cwe.get(cwe_id, []):
                    if rule["id"] not in seen:
                        seen.add(rule["id"])
                        req["refs"].append({
                            "source": "cert",
                            "id": rule["id"],
                            "name": rule["name"],
                            "url": rule.get("source_url", _CERT_MAIN_URL),
                        })
            for cert_id in req["_cert_ids"]:
                if cert_id not in seen and cert_id in cert_by_id:
                    rule = cert_by_id[cert_id]
                    seen.add(cert_id)
                    req["refs"].append({
                        "source": "cert",
                        "id": rule["id"],
                        "name": rule["name"],
                        "url": rule.get("source_url", _CERT_MAIN_URL),
                    })


def _attach_wcag_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach WCAG cross-references to requirements with wcag fields."""
    if dimension not in WCAG_DIMENSIONS:
        return
    wcag_file = standards_dir / "wcag" / "level_a.json"
    if not wcag_file.exists():
        return
    wcag_data = json.loads(wcag_file.read_text())
    wcag_lookup = {c["id"]: c for c in wcag_data.get("criteria", [])}
    for reqs in index.values():
        for req in reqs:
            for wcag_id in req["_wcag_ids"]:
                if wcag_id in wcag_lookup:
                    c = wcag_lookup[wcag_id]
                    req["refs"].append({
                        "source": "wcag22",
                        "id": wcag_id,
                        "name": c["name"],
                        "url": c.get("url", "https://www.w3.org/TR/WCAG22/"),
                    })


def build_req_index(
    standards_dir: Path,
    dimension: str,
    cwe_db: object | None = None,
) -> dict[str, list[dict]]:
    """Build a principle -> [requirement] index for a dimension.

    Returns: {"Fault Tolerance": [{"id": "R-FT-1", "source": "iso25010", "text": "...", "refs": [...]}]}
    """
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())
    index = _build_req_index(iso_data)
    _attach_cwe_refs(index, cwe_db)
    _attach_cisq_refs(index, standards_dir, dimension)
    _attach_asvs_refs(index, standards_dir, dimension)
    _attach_cert_refs(index, standards_dir, dimension)
    _attach_wcag_refs(index, standards_dir, dimension)
    return index


def compile_dimension(standards_dir: Path, dimension: str, cwe_db=None) -> dict:
    """Compile a single dimension into the requirement-centric output format."""
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())

    index = build_req_index(standards_dir, dimension, cwe_db)

    sources = ["iso25010"]
    if dimension in CISQ_DIMENSIONS:
        sources.append("cisq")
    if dimension == "security":
        sources.append("asvs")
    if dimension in CERT_DIMENSIONS:
        sources.append("cert")
    if dimension in WCAG_DIMENSIONS:
        sources.append("wcag22")

    principles = []
    for principle_name, reqs in index.items():
        req_list = []
        for req in reqs:
            r = {k: v for k, v in req.items() if not k.startswith("_")}
            req_list.append(r)
        principles.append({
            "name": principle_name,
            "source": "iso25010",
            "requirements": req_list,
        })

    return {
        "id": dimension,
        "name": iso_data.get("name", dimension.title()),
        "sources": sources,
        "principles": principles,
    }


def report_gaps(standards_dir: Path, dimension: str) -> list[str]:
    """Report CISQ CWEs not found in any ISO 25010 requirement."""
    if dimension not in CISQ_DIMENSIONS:
        return []

    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())
    iso_cwes: set[int] = set()
    for sc in iso_data.get("sub_characteristics", []):
        for req in sc.get("requirements", []):
            iso_cwes.update(req.get("cwe", []))

    cisq_file = standards_dir / "cisq" / f"{dimension}.json"
    cisq_data = json.loads(cisq_file.read_text())
    cisq_lookup = {c["id"]: c["name"] for c in cisq_data.get("cwes", [])}

    warnings = []
    for cwe_id, name in sorted(cisq_lookup.items()):
        if cwe_id not in iso_cwes:
            warnings.append(f"orphan: CWE-{cwe_id} ({name}) not in any {dimension} principle")
    return warnings


def main() -> None:
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
        n_reqs = sum(len(p["requirements"]) for p in compiled["principles"])
        print(f"  {dim}: {n_principles} principles, {n_reqs} requirements -> {out_file}")


if __name__ == "__main__":
    main()
