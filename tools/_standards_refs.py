"""Helper functions for attaching cross-references to compiled standards.

Extracted from compile_standards.py to keep that module under 300 lines.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from quodeq.shared.utils import read_json as _read_json

_ASVS_MAIN_URL = "https://owasp.org/www-project-application-security-verification-standard/"
_CISQ_MAIN_URL = "https://www.it-cisq.org/coding-rules/"
_CERT_MAIN_URL = "https://wiki.sei.cmu.edu/confluence/display/seccode"
_WCAG22_MAIN_URL = "https://www.w3.org/TR/WCAG22/"

CISQ_DIMENSIONS = {"maintainability", "security", "reliability", "performance"}
WCAG_DIMENSIONS = {"usability"}
CERT_DIMENSIONS = {"reliability"}

_ASVS_FILE = "asvs/level1.json"
_WCAG_FILE = "wcag/level_a.json"

_logger = logging.getLogger(__name__)


def attach_cwe_refs(index: dict[str, list[dict]], cwe_db: object | None, get_cwe_name: Callable[..., str]) -> None:
    """Add a CWE ref for each CWE ID referenced by a requirement."""
    for reqs in index.values():
        for req in reqs:
            for cwe_id in req["_cwe_ids"]:
                name = get_cwe_name(cwe_db, cwe_id) if cwe_db else f"CWE-{cwe_id}"
                req["refs"].append({
                    "source": "cwe",
                    "id": str(cwe_id),
                    "name": name,
                    "url": f"https://cwe.mitre.org/data/definitions/{cwe_id}.html",
                })


def attach_cisq_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach CISQ cross-references to requirements whose CWEs appear in CISQ."""
    if dimension not in CISQ_DIMENSIONS:
        return
    cisq_file = standards_dir / "cisq" / f"{dimension}.json"
    if not cisq_file.exists():
        return
    try:
        cisq_data = _read_json(cisq_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.warning("Skipping CISQ refs for %s: %s", dimension, exc)
        return
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


def _collect_asvs_refs_for_req(req: dict, asvs_by_cwe: dict[int, list[dict]]) -> None:
    """Append ASVS refs to a single requirement, deduplicating by ID."""
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


def attach_asvs_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach ASVS cross-references (security dimension only)."""
    if dimension != "security":
        return
    asvs_file = standards_dir / _ASVS_FILE
    if not asvs_file.exists():
        return
    try:
        asvs_data = _read_json(asvs_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.warning("Skipping ASVS refs: %s", exc)
        return
    asvs_by_cwe: dict[int, list[dict]] = {}
    for r in asvs_data.get("requirements", []):
        for cwe_id in r.get("cwe", []):
            asvs_by_cwe.setdefault(cwe_id, []).append(r)
    for reqs in index.values():
        for req in reqs:
            _collect_asvs_refs_for_req(req, asvs_by_cwe)


def _collect_cert_refs_for_req(
    req: dict, cert_by_cwe: dict[int, list[dict]], cert_by_id: dict[str, dict],
) -> None:
    """Append CERT refs to a single requirement, deduplicating by ID."""
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


def attach_cert_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach CERT cross-references via CWE matching and explicit cert fields."""
    if dimension not in CERT_DIMENSIONS:
        return
    cert_file = standards_dir / "cert" / f"{dimension}.json"
    if not cert_file.exists():
        return
    try:
        cert_data = _read_json(cert_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.warning("Skipping CERT refs for %s: %s", dimension, exc)
        return
    cert_by_cwe: dict[int, list[dict]] = {}
    cert_by_id: dict[str, dict] = {}
    for rule in cert_data.get("rules", []):
        cert_by_id[rule["id"]] = rule
        for cwe_id in rule.get("cwe", []):
            cert_by_cwe.setdefault(cwe_id, []).append(rule)
    for reqs in index.values():
        for req in reqs:
            _collect_cert_refs_for_req(req, cert_by_cwe, cert_by_id)


def attach_wcag_refs(index: dict[str, list[dict]], standards_dir: Path, dimension: str) -> None:
    """Attach WCAG cross-references to requirements with wcag fields."""
    if dimension not in WCAG_DIMENSIONS:
        return
    wcag_file = standards_dir / _WCAG_FILE
    if not wcag_file.exists():
        return
    try:
        wcag_data = _read_json(wcag_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _logger.warning("Skipping WCAG refs: %s", exc)
        return
    wcag_lookup = {c["id"]: c for c in wcag_data.get("criteria", [])}
    for reqs in index.values():
        for req in reqs:
            seen: set[str] = set()
            for wcag_id in req["_wcag_ids"]:
                if wcag_id in wcag_lookup and wcag_id not in seen:
                    seen.add(wcag_id)
                    c = wcag_lookup[wcag_id]
                    req["refs"].append({
                        "source": "wcag22",
                        "id": wcag_id,
                        "name": c["name"],
                        "url": c.get("url", _WCAG22_MAIN_URL),
                    })
