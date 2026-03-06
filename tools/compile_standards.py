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

STANDARDS_DIR = repo_root / "v2" / "standards"
OUTPUT_DIR = STANDARDS_DIR / "compiled"

ALL_DIMENSIONS = ["maintainability", "security", "reliability", "performance",
                  "usability", "flexibility"]

CISQ_DIMENSIONS = {"maintainability", "security", "reliability", "performance"}


def _load_cwe_names():
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
    """Build a principle -> {cwe_id -> {name, refs}} index for a dimension.

    Returns: {"Modularity": {1121: {"name": "...", "refs": [...]}}, ...}
    """
    iso_file = standards_dir / "iso25010" / f"{dimension}.json"
    iso_data = json.loads(iso_file.read_text())

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
        print(f"  {dim}: {n_principles} principles, {n_cwes} CWEs -> {out_file}")


if __name__ == "__main__":
    main()
