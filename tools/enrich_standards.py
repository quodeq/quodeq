#!/usr/bin/env python3
"""One-time enrichment script: adds ~250 CWEs from CWE Top 25, OWASP 2025,
CISQ 2020, and Quality Weaknesses views into ISO 25010 files.

Usage:
    python3 tools/enrich_standards.py                # dry-run (shows what would be added)
    python3 tools/enrich_standards.py --apply         # actually writes files
    python3 tools/enrich_standards.py --apply --compile  # writes + recompiles + re-resolves
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Ensure tools/ is on sys.path so we can import sibling modules.
_tools_dir = str(Path(__file__).resolve().parent)
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

_TEXT_ENCODING = "utf-8"
STANDARDS_DIR = Path(__file__).resolve().parent.parent / "standards" / "iso25010"

# ---------------------------------------------------------------------------
# Mapping: dimension → principle → [[requirement_text, [cwe_ids]]]
#
# Loaded from the companion JSON file. Each [text, cwes] pair becomes one
# requirement entry. CWE IDs already present in the file are silently skipped.
# ---------------------------------------------------------------------------

_MAPPING_PATH = Path(__file__).resolve().parent / "enrich_standards_mapping.json"
_PREFIX_MAP_PATH = Path(__file__).resolve().parent / "enrich_standards_prefix_map.json"

# Lazily loaded at first use (avoids file reads at import time).
_UNKNOWN_PREFIX = "X-XXX"
_lazy_cache: dict[str, dict] = {}


def _load_mapping() -> dict:
    """Load and cache the enrichment mapping from disk."""
    if "mapping" not in _lazy_cache:
        try:
            _lazy_cache["mapping"] = json.loads(_MAPPING_PATH.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot load mapping file {_MAPPING_PATH}: {exc}") from exc
    return _lazy_cache["mapping"]


def _load_prefix_map() -> dict:
    """Load and cache the prefix map from disk."""
    if "prefix_map" not in _lazy_cache:
        try:
            _lazy_cache["prefix_map"] = json.loads(_PREFIX_MAP_PATH.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot load prefix map {_PREFIX_MAP_PATH}: {exc}") from exc
    return _lazy_cache["prefix_map"]


def _get_existing_cwes(data: dict) -> set[int]:
    """Extract all CWE IDs already present in an ISO 25010 file."""
    cwes: set[int] = set()
    for sc in data.get("sub_characteristics", []):
        for req in sc.get("requirements", []):
            for c in req.get("cwe", []):
                cwes.add(c)
    return cwes


def _get_highest_id(reqs: list[dict], prefix: str) -> int:
    """Find the highest numbered requirement ID for a given prefix."""
    highest = 0
    for req in reqs:
        rid = req.get("id", "")
        if rid.startswith(prefix + "-"):
            try:
                num = int(rid.split("-")[-1])
                highest = max(highest, num)
            except ValueError:
                pass
    return highest


def enrich_dimension(dimension: str, dry_run: bool = True) -> int:
    """Add missing CWEs to one ISO 25010 dimension file. Returns count added."""
    mapping = _load_mapping()
    if dimension not in mapping:
        return 0

    filepath = STANDARDS_DIR / f"{dimension}.json"
    if not filepath.exists():
        print(f"  SKIP {dimension}: file not found")
        return 0

    data = json.loads(filepath.read_text(encoding=_TEXT_ENCODING))
    existing = _get_existing_cwes(data)
    prefixes = _load_prefix_map().get(dimension, {})
    total_added = 0

    for sc in data["sub_characteristics"]:
        sc_name = sc["name"]
        if sc_name not in mapping[dimension]:
            continue

        prefix = prefixes.get(sc_name, _UNKNOWN_PREFIX)
        highest = _get_highest_id(sc["requirements"], prefix)

        for req_text, cwe_ids in mapping[dimension][sc_name]:
            # Filter out CWEs that already exist
            new_cwes = [c for c in cwe_ids if c not in existing]
            if not new_cwes:
                continue

            highest += 1
            new_req = {
                "id": f"{prefix}-{highest}",
                "text": req_text,
                "cwe": sorted(new_cwes),
            }
            sc["requirements"].append(new_req)
            existing.update(new_cwes)
            total_added += len(new_cwes)

            if dry_run:
                print(f"  {new_req['id']}: {len(new_cwes)} CWEs → {sc_name}")

    if not dry_run and total_added > 0:
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding=_TEXT_ENCODING)
        print(f"  Wrote {filepath.name} (+{total_added} CWEs)")

    return total_added


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich ISO 25010 with CWEs from external views")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument("--compile", action="store_true", help="Run compile + resolve after applying")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN — use --apply to write changes\n")

    from compile_standards import ALL_DIMENSIONS

    grand_total = 0
    for dimension in ALL_DIMENSIONS:
        print(f"\n{'='*60}")
        print(f"  {dimension.upper()}")
        print(f"{'='*60}")
        count = enrich_dimension(dimension, dry_run=dry_run)
        grand_total += count
        print(f"  Total new CWEs for {dimension}: {count}")

    print(f"\n{'='*60}")
    print(f"  GRAND TOTAL: {grand_total} new CWEs")
    print(f"{'='*60}")

    if args.apply and args.compile:
        print("\nRecompiling standards...")
        tools_dir = Path(__file__).resolve().parent
        subprocess.run([sys.executable, str(tools_dir / "compile_standards.py")], check=True)
        print("\nRunning gap report...")
        subprocess.run([sys.executable, str(tools_dir / "compile_standards.py"), "--gaps"], check=True)


if __name__ == "__main__":
    main()
