#!/usr/bin/env python3
"""Audit all CWEs in ISO 25010 files for abstraction level and mapping usage.

Uses the CWE REST API: https://cwe-api.mitre.org/api/v1/cwe/weakness/{id}

Usage:
    python3 tools/audit_cwe_abstraction.py           # audit all CWEs
    python3 tools/audit_cwe_abstraction.py --problems # show only PROHIBITED/DISCOURAGED
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

STANDARDS_DIR = Path(__file__).resolve().parent.parent / "standards" / "iso25010"
API_BASE = "https://cwe-api.mitre.org/api/v1/cwe/weakness"


def get_all_cwes() -> dict[int, list[str]]:
    """Extract all CWE IDs from ISO 25010 files, mapped to their dimension(s)."""
    cwe_dims: dict[int, list[str]] = {}
    for filepath in sorted(STANDARDS_DIR.glob("*.json")):
        data = json.loads(filepath.read_text())
        dimension = data.get("id", filepath.stem)
        for sc in data.get("sub_characteristics", []):
            for req in sc.get("requirements", []):
                for cwe_id in req.get("cwe", []):
                    cwe_dims.setdefault(cwe_id, []).append(dimension)
    return cwe_dims


def fetch_cwe_info(cwe_id: int) -> dict | None:
    """Fetch abstraction and mapping info from CWE API."""
    url = f"{API_BASE}/{cwe_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "Weaknesses" in data and data["Weaknesses"]:
                w = data["Weaknesses"][0]
                mapping_notes = w.get("MappingNotes", {})
                return {
                    "id": cwe_id,
                    "name": w.get("Name", ""),
                    "abstraction": w.get("Abstraction", "Unknown"),
                    "status": w.get("Status", ""),
                    "mapping_usage": mapping_notes.get("Usage", "Unknown"),
                    "mapping_rationale": mapping_notes.get("Rationale", ""),
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return _fetch_category_info(cwe_id) or _fetch_view_info(cwe_id)
        print(f"  HTTP {e.code} for CWE-{cwe_id}", file=sys.stderr)
    except Exception as e:
        print(f"  Error for CWE-{cwe_id}: {e}", file=sys.stderr)
    return None


def _fetch_category_info(cwe_id: int) -> dict | None:
    """Try fetching as a category if weakness lookup returned 404."""
    url = f"https://cwe-api.mitre.org/api/v1/cwe/category/{cwe_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "Categories" in data and data["Categories"]:
                c = data["Categories"][0]
                mapping_notes = c.get("MappingNotes", {})
                return {
                    "id": cwe_id,
                    "name": c.get("Name", ""),
                    "abstraction": "Category",
                    "status": c.get("Status", ""),
                    "mapping_usage": mapping_notes.get("Usage", "Prohibited"),
                    "mapping_rationale": "Categories are not weaknesses",
                }
    except Exception:
        pass
    return None


def _fetch_view_info(cwe_id: int) -> dict | None:
    """Try fetching as a view if category lookup also returned 404."""
    url = f"https://cwe-api.mitre.org/api/v1/cwe/view/{cwe_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if "Views" in data and data["Views"]:
                v = data["Views"][0]
                return {
                    "id": cwe_id,
                    "name": v.get("Name", ""),
                    "abstraction": "View",
                    "status": v.get("Status", ""),
                    "mapping_usage": "Prohibited",
                    "mapping_rationale": "Views are not weaknesses",
                }
    except Exception:
        pass
    return None


# Prohibited CWEs that are true empty categories (no weakness semantics)
_TRUE_CATEGORIES = {16, 310, 320, 1002, 1035}
_DEPRECATED = {391}


def _compute_llm_mapping_usage(cwe_id: int, mapping_usage: str, abstraction: str) -> str:
    """Derive llm_mapping_usage from MITRE metadata."""
    if mapping_usage in ("Allowed", "Allowed-with-Review"):
        return "Allowed"
    if mapping_usage == "Discouraged":
        return "Discouraged" if abstraction == "Pillar" else "Allowed-with-Review"
    if mapping_usage == "Prohibited":
        if cwe_id in _TRUE_CATEGORIES or abstraction in ("Category", "View"):
            return "Prohibited"
        if cwe_id in _DEPRECATED:
            return "Discouraged"
        return "Allowed"  # structural/quality metrics — LLM can reason about these
    return "Allowed-with-Review"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problems", action="store_true", help="Show only PROHIBITED/DISCOURAGED")
    args = parser.parse_args()

    cwe_dims = get_all_cwes()
    print(f"Total unique CWEs in ISO 25010 files: {len(cwe_dims)}\n")

    results: list[dict] = []
    for i, cwe_id in enumerate(sorted(cwe_dims.keys()), 1):
        info = fetch_cwe_info(cwe_id)
        if info:
            info["dimensions"] = cwe_dims[cwe_id]
            info["fetched_date"] = str(date.today())
            info["llm_mapping_usage"] = _compute_llm_mapping_usage(
                info["id"], info["mapping_usage"], info["abstraction"]
            )
            results.append(info)
        if i % 20 == 0:
            print(f"  Fetched {i}/{len(cwe_dims)}...", file=sys.stderr)
        time.sleep(0.1)  # rate limit

    # Categorize
    prohibited = [r for r in results if r["mapping_usage"].lower() == "prohibited"]
    discouraged = [r for r in results if r["mapping_usage"].lower() == "discouraged"]
    allowed = [r for r in results if r["mapping_usage"].lower() in ("allowed", "allowed-with-review")]
    unknown = [r for r in results if r["mapping_usage"].lower() not in ("prohibited", "discouraged", "allowed", "allowed-with-review")]

    if not args.problems:
        print(f"\n{'='*80}")
        print(f"SUMMARY")
        print(f"{'='*80}")
        print(f"  ALLOWED:          {len(allowed)}")
        print(f"  DISCOURAGED:      {len(discouraged)}")
        print(f"  PROHIBITED:       {len(prohibited)}")
        print(f"  Unknown/Other:    {len(unknown)}")

    if prohibited:
        print(f"\n{'='*80}")
        print(f"PROHIBITED ({len(prohibited)}) — Must be removed")
        print(f"{'='*80}")
        for r in prohibited:
            print(f"  CWE-{r['id']:4d} [{r['abstraction']:10s}] {r['name']}")
            print(f"           Dimensions: {', '.join(r['dimensions'])}")
            if r["mapping_rationale"]:
                print(f"           Rationale: {r['mapping_rationale'][:120]}")

    if discouraged:
        print(f"\n{'='*80}")
        print(f"DISCOURAGED ({len(discouraged)}) — Should use more specific children")
        print(f"{'='*80}")
        for r in discouraged:
            print(f"  CWE-{r['id']:4d} [{r['abstraction']:10s}] {r['name']}")
            print(f"           Dimensions: {', '.join(r['dimensions'])}")

    if unknown and not args.problems:
        print(f"\n{'='*80}")
        print(f"UNKNOWN/OTHER ({len(unknown)})")
        print(f"{'='*80}")
        for r in unknown:
            print(f"  CWE-{r['id']:4d} [{r['abstraction']:10s}] Usage={r['mapping_usage']} — {r['name']}")

    # Write full results to JSON for further processing
    output_path = Path(__file__).resolve().parent.parent / "standards" / "cwe" / "audit.json"
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"\nFull results written to {output_path}")


if __name__ == "__main__":
    main()
