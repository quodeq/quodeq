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

from _standards_refs import (
    CERT_DIMENSIONS,
    CISQ_DIMENSIONS,
    WCAG_DIMENSIONS,
    attach_asvs_refs,
    attach_cert_refs,
    attach_cisq_refs,
    attach_cwe_refs,
    attach_wcag_refs,
)

repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

_TEXT_ENCODING = "utf-8"
STANDARDS_DIR = repo_root / "standards"
OUTPUT_DIR = STANDARDS_DIR / "compiled"

ALL_DIMENSIONS = ["maintainability", "security", "reliability", "performance",
                  "usability", "flexibility"]


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


def _load_iso_data(standards_dir: Path, dimension: str) -> dict:
    """Read and parse the ISO 25010 JSON file for *dimension*."""
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    try:
        return json.loads(iso_file.read_text(encoding=_TEXT_ENCODING))
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read ISO 25010 file {iso_file}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot read ISO 25010 file {iso_file}: {exc}") from exc


def build_req_index(
    standards_dir: Path,
    dimension: str,
    cwe_db: object | None = None,
    iso_data: dict | None = None,
) -> dict[str, list[dict]]:
    """Build a principle -> [requirement] index for a dimension.

    *iso_data* may be passed to avoid re-reading the ISO file when the
    caller already has it loaded.

    Returns: {"Fault Tolerance": [{"id": "R-FT-1", "source": "iso25010", "text": "...", "refs": [...]}]}
    """
    if iso_data is None:
        iso_data = _load_iso_data(standards_dir, dimension)
    index = _build_req_index(iso_data)
    attach_cwe_refs(index, cwe_db, _get_cwe_name)
    attach_cisq_refs(index, standards_dir, dimension)
    attach_asvs_refs(index, standards_dir, dimension)
    attach_cert_refs(index, standards_dir, dimension)
    attach_wcag_refs(index, standards_dir, dimension)
    return index


def compile_dimension(standards_dir: Path, dimension: str, cwe_db=None) -> dict:
    """Compile a single dimension into the requirement-centric output format."""
    iso_data = _load_iso_data(standards_dir, dimension)
    dim_name = iso_data.get("name", dimension.title())
    index = build_req_index(standards_dir, dimension, cwe_db, iso_data=iso_data)

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
        "name": dim_name,
        "sources": sources,
        "principles": principles,
    }


def report_gaps(standards_dir: Path, dimension: str) -> list[str]:
    """Report CISQ CWEs not found in any ISO 25010 requirement."""
    if dimension not in CISQ_DIMENSIONS:
        return []

    iso_data = _load_iso_data(standards_dir, dimension)
    iso_cwes: set[int] = set()
    for sc in iso_data.get("sub_characteristics", []):
        for req in sc.get("requirements", []):
            iso_cwes.update(req.get("cwe", []))

    cisq_file = standards_dir / "cisq" / f"{dimension}.json"
    if not cisq_file.exists():
        return []
    try:
        cisq_data = json.loads(cisq_file.read_text(encoding=_TEXT_ENCODING))
    except OSError as exc:
        raise FileNotFoundError(f"Cannot read CISQ file {cisq_file}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot read CISQ file {cisq_file}: {exc}") from exc
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
        out_file.write_text(json.dumps(compiled, indent=2) + "\n", encoding=_TEXT_ENCODING)
        n_principles = len(compiled["principles"])
        n_reqs = sum(len(p["requirements"]) for p in compiled["principles"])
        print(f"  {dim}: {n_principles} principles, {n_reqs} requirements -> {out_file}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError) as _exc:
        raise SystemExit(str(_exc)) from _exc
