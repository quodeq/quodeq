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

_PROGRESS_LOG_INTERVAL = 20
_RATE_LIMIT_SLEEP_S = 0.1
_TERMINAL_WIDTH = 80
_MAX_RATIONALE_DISPLAY = 120

_API_TIMEOUT_S = 10

_ALLOWED_USAGES = {"allowed", "allowed-with-review"}
_KNOWN_USAGES = {"prohibited", "discouraged"} | _ALLOWED_USAGES

_DEFAULT_STANDARDS_DIR = Path(__file__).resolve().parent.parent / "standards" / "iso25010"
_DEFAULT_API_BASE = "https://cwe-api.mitre.org/api/v1/cwe"


def get_all_cwes(standards_dir: Path | None = None) -> dict[int, list[str]]:
    """Extract all CWE IDs from ISO 25010 files, mapped to their dimension(s)."""
    base = standards_dir or _DEFAULT_STANDARDS_DIR
    cwe_dims: dict[int, list[str]] = {}
    for filepath in sorted(base.glob("*.json")):
        data = json.loads(filepath.read_text())
        dimension = data.get("id", filepath.stem)
        for sc in data.get("sub_characteristics", []):
            for req in sc.get("requirements", []):
                for cwe_id in req.get("cwe", []):
                    cwe_dims.setdefault(cwe_id, []).append(dimension)
    return cwe_dims


def _fetch_cwe_endpoint(
    endpoint: str, collection_key: str, cwe_id: int, api_base: str,
) -> dict | None:
    """Fetch a CWE entity from *endpoint* and return the first item under *collection_key*."""
    url = f"{api_base}/{endpoint}/{cwe_id}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_API_TIMEOUT_S) as resp:
            data = json.loads(resp.read())
            items = data.get(collection_key, [])
            return items[0] if items else None
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def fetch_cwe_info(cwe_id: int, api_base: str = _DEFAULT_API_BASE) -> dict | None:
    """Fetch abstraction and mapping info from CWE API."""
    w = _fetch_cwe_endpoint("weakness", "Weaknesses", cwe_id, api_base)
    if w is not None:
        mapping_notes = w.get("MappingNotes", {})
        return {
            "id": cwe_id,
            "name": w.get("Name", ""),
            "abstraction": w.get("Abstraction", "Unknown"),
            "status": w.get("Status", ""),
            "mapping_usage": mapping_notes.get("Usage", "Unknown"),
            "mapping_rationale": mapping_notes.get("Rationale", ""),
        }
    # 404 from weakness — try category then view
    cat = _fetch_cwe_endpoint("category", "Categories", cwe_id, api_base)
    if cat is not None:
        mapping_notes = cat.get("MappingNotes", {})
        return {
            "id": cwe_id,
            "name": cat.get("Name", ""),
            "abstraction": "Category",
            "status": cat.get("Status", ""),
            "mapping_usage": mapping_notes.get("Usage", "Prohibited"),
            "mapping_rationale": "Categories are not weaknesses",
        }
    view = _fetch_cwe_endpoint("view", "Views", cwe_id, api_base)
    if view is not None:
        return {
            "id": cwe_id,
            "name": view.get("Name", ""),
            "abstraction": "View",
            "status": view.get("Status", ""),
            "mapping_usage": "Prohibited",
            "mapping_rationale": "Views are not weaknesses",
        }
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


def _categorize_results(results: list[dict]) -> dict[str, list[dict]]:
    """Sort results into prohibited/discouraged/allowed/unknown buckets."""
    categorized: dict[str, list[dict]] = {"prohibited": [], "discouraged": [], "allowed": [], "unknown": []}
    for r in results:
        usage = r["mapping_usage"].lower()
        if usage == "prohibited":
            categorized["prohibited"].append(r)
        elif usage == "discouraged":
            categorized["discouraged"].append(r)
        elif usage in _ALLOWED_USAGES:
            categorized["allowed"].append(r)
        else:
            categorized["unknown"].append(r)
    return categorized


def _print_category(label: str, entries: list[dict], *, show_rationale: bool = False) -> None:
    """Print a single category section."""
    print(f"\n{'=' * _TERMINAL_WIDTH}")
    print(f"{label}")
    print(f"{'=' * _TERMINAL_WIDTH}")
    for r in entries:
        print(f"  CWE-{r['id']:4d} [{r['abstraction']:10s}] {r['name']}")
        print(f"           Dimensions: {', '.join(r['dimensions'])}")
        if show_rationale and r["mapping_rationale"]:
            print(f"           Rationale: {r['mapping_rationale'][:_MAX_RATIONALE_DISPLAY]}")


def _print_results(results: list[dict], *, problems_only: bool) -> None:
    """Print categorized audit results to stdout and write JSON output."""
    categorized = _categorize_results(results)
    prohibited = categorized["prohibited"]
    discouraged = categorized["discouraged"]
    allowed = categorized["allowed"]
    unknown = categorized["unknown"]

    if not problems_only:
        print(f"\n{'=' * _TERMINAL_WIDTH}")
        print("SUMMARY")
        print(f"{'=' * _TERMINAL_WIDTH}")
        print(f"  ALLOWED:          {len(allowed)}")
        print(f"  DISCOURAGED:      {len(discouraged)}")
        print(f"  PROHIBITED:       {len(prohibited)}")
        print(f"  Unknown/Other:    {len(unknown)}")

    if prohibited:
        _print_category(f"PROHIBITED ({len(prohibited)}) — Must be removed", prohibited, show_rationale=True)
    if discouraged:
        _print_category(f"DISCOURAGED ({len(discouraged)}) — Should use more specific children", discouraged)
    if unknown and not problems_only:
        print(f"\n{'=' * _TERMINAL_WIDTH}")
        print(f"UNKNOWN/OTHER ({len(unknown)})")
        print(f"{'=' * _TERMINAL_WIDTH}")
        for r in unknown:
            print(f"  CWE-{r['id']:4d} [{r['abstraction']:10s}] Usage={r['mapping_usage']} — {r['name']}")

    output_path = Path(__file__).resolve().parent.parent / "standards" / "cwe" / "audit.json"
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print(f"\nFull results written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--problems", action="store_true", help="Show only PROHIBITED/DISCOURAGED")
    parser.add_argument(
        "--standards-dir", type=Path, default=_DEFAULT_STANDARDS_DIR,
        help=f"ISO 25010 standards directory (default: {_DEFAULT_STANDARDS_DIR})",
    )
    parser.add_argument(
        "--api-base",
        default=_DEFAULT_API_BASE,
        help=f"CWE REST API base URL (default: {_DEFAULT_API_BASE})",
    )
    args = parser.parse_args()
    api_base: str = args.api_base

    cwe_dims = get_all_cwes(args.standards_dir)
    print(f"Total unique CWEs in ISO 25010 files: {len(cwe_dims)}\n")

    results: list[dict] = []
    for i, cwe_id in enumerate(sorted(cwe_dims.keys()), 1):
        info = fetch_cwe_info(cwe_id, api_base)
        if info:
            info["dimensions"] = cwe_dims[cwe_id]
            info["fetched_date"] = str(date.today())
            info["llm_mapping_usage"] = _compute_llm_mapping_usage(
                info["id"], info["mapping_usage"], info["abstraction"]
            )
            results.append(info)
        if i % _PROGRESS_LOG_INTERVAL == 0:
            print(f"  Fetched {i}/{len(cwe_dims)}...", file=sys.stderr)
        time.sleep(_RATE_LIMIT_SLEEP_S)

    _print_results(results, problems_only=args.problems)


if __name__ == "__main__":
    main()
