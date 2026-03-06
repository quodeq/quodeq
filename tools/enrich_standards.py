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

STANDARDS_DIR = Path(__file__).resolve().parent.parent / "v2" / "standards" / "iso25010"

# ---------------------------------------------------------------------------
# Mapping: dimension → principle → [(requirement_text, [cwe_ids])]
#
# Each (text, cwes) pair becomes one requirement entry.
# CWE IDs that already exist in the file are silently skipped.
# ---------------------------------------------------------------------------

MAPPING: dict[str, dict[str, list[tuple[str, list[int]]]]] = {
    # ===================================================================
    # SECURITY
    # ===================================================================
    "security": {
        "Confidentiality": [
            (
                "Cryptographic algorithms and key management MUST use strong, current implementations",
                [261, 296, 320, 321, 322, 323, 324, 325, 327, 328, 329,
                 332, 334, 335, 336, 337, 338, 340, 342, 347, 757, 759,
                 760, 780, 916, 1240, 1241],
            ),
            (
                "Sensitive data MUST NOT be stored in cleartext in files, cookies, memory, or environment variables",
                [256, 258, 260, 312, 313, 315, 316, 526],
            ),
            (
                "Sensitive information MUST NOT be exposed through source code, comments, error messages, or debug output",
                [201, 209, 215, 219, 359, 402, 538, 540, 550, 615],
            ),
            (
                "File and resource permissions MUST follow the principle of least privilege",
                [276, 281, 282, 283, 732],
            ),
            (
                "Credentials MUST be protected during transport and storage",
                [522],
            ),
            (
                "Resources MUST NOT be exposed to wrong spheres",
                [668],
            ),
        ],
        "Integrity": [
            (
                "Application MUST neutralize all injection vectors including command, expression, CRLF, header, and query injection",
                [74, 76, 77, 80, 83, 86, 88, 91, 93, 96, 97, 99,
                 112, 113, 114, 115, 129, 134, 470, 564, 610, 644,
                 652, 917],
            ),
            (
                "Software components MUST be verified for integrity, kept updated, and free from known vulnerabilities",
                [345, 426, 427, 447, 477, 494, 506, 565, 784,
                 1035, 1329, 1357, 1395],
            ),
            (
                "Request and file interpretation MUST be consistent and resistant to smuggling or confusion attacks",
                [436, 444, 646],
            ),
            (
                "Application design MUST follow secure design principles including defense in depth and fail-safe defaults",
                [362, 382, 451, 454, 501, 628, 642, 653, 656, 657,
                 676, 693, 807, 1022, 1125],
            ),
            (
                "Input validation MUST use strict allowlists and verify boundary conditions",
                [183, 606],
            ),
        ],
        "Authenticity": [
            (
                "Authentication MUST resist spoofing, replay, certificate, and bypass attempts across all channels",
                [288, 289, 290, 291, 293, 294, 297, 298, 299, 300,
                 302, 303, 305, 308, 309],
            ),
            (
                "Credentials MUST be unique, non-default, and sufficiently protected against disclosure",
                [940, 941, 1390, 1391, 1392, 1393],
            ),
            (
                "Authorization MUST be enforced server-side with proper privilege management and least-privilege access",
                [266, 269, 284, 286, 425, 441, 472, 566, 862, 863],
            ),
            (
                "Missing encryption of sensitive data MUST NOT weaken authentication guarantees",
                [311],
            ),
        ],
        "Accountability": [
            (
                "Security-relevant events MUST be logged with neutralized output and sufficient detail",
                [117, 221, 223, 778],
            ),
            (
                "Security configuration MUST disable debug features, restrict cross-domain policies, and limit recursive entity expansion in production",
                [15, 489, 547, 776, 942],
            ),
            (
                "Custom error pages MUST be used and MUST NOT reveal implementation details",
                [756],
            ),
        ],
        "Non-repudiation": [
            (
                "Application MUST protect against UI redress and clickjacking through untrusted web content inclusion",
                [379],
            ),
        ],
    },

    # ===================================================================
    # RELIABILITY
    # ===================================================================
    "reliability": {
        "Fault Tolerance": [
            (
                "Error conditions MUST be detected and handled, not silently ignored",
                [248, 274, 280, 369, 390, 391, 394, 460, 550, 636, 703, 755],
            ),
            (
                "Switch statements MUST include default cases and break statements",
                [478, 484],
            ),
            (
                "Incorrect operators and type conversions MUST be avoided",
                [480, 595, 681, 704],
            ),
            (
                "Custom error pages MUST NOT reveal sensitive implementation details",
                [234, 756],
            ),
        ],
        "Maturity": [
            (
                "Resources MUST be properly initialized before use",
                [456, 665, 908],
            ),
            (
                "Concurrent access to shared resources MUST be properly synchronized",
                [662, 820, 821, 833],
            ),
            (
                "Calculations and comparisons MUST be correct and avoid undefined behavior",
                [682, 758],
            ),
            (
                "NULL pointer dereference MUST be prevented through proper null checks",
                [476],
            ),
        ],
        "Recoverability": [
            (
                "Resources MUST be properly released and cleaned up after use",
                [404, 459, 672],
            ),
        ],
        "Availability": [
            (
                "Operations on expired or released resources MUST be prevented",
                [1088],
            ),
        ],
    },

    # ===================================================================
    # MAINTAINABILITY
    # ===================================================================
    "maintainability": {
        "Modularity": [
            (
                "Class hierarchies MUST avoid excessive depth, circular dependencies, and improper virtual destructor patterns",
                [1042, 1043, 1047, 1055, 1062, 1079, 1086, 1087],
            ),
            (
                "Functions MUST NOT have variadic parameters without type safety or excessive file/data access operations",
                [1056, 1060, 1073, 1084],
            ),
            (
                "Code MUST maintain proper encapsulation and data element visibility",
                [766, 1061, 1092],
            ),
            (
                "Modules MUST NOT have hard-coded network configuration or platform-dependent components",
                [1051, 1100, 1102, 1103, 1105],
            ),
        ],
        "Analyzability": [
            (
                "Code complexity MUST remain within measurable thresholds (Halstead, nesting depth, attack surface)",
                [1120, 1122, 1124, 1125],
            ),
            (
                "Source code MUST follow consistent naming, formatting, and style conventions",
                [710, 1076, 1078, 1099, 1113, 1114, 1115],
            ),
            (
                "Code MUST NOT contain dead code, empty blocks, irrelevant code, or redundant expressions",
                [561, 570, 571, 783, 1041, 1069, 1071, 1119, 1164],
            ),
            (
                "Documentation MUST be sufficient, accurate, and consistent with the implementation",
                [1053, 1068, 1110, 1111, 1112, 1116, 1117, 1118],
            ),
            (
                "Variables MUST be used for their declared purpose with appropriate scope",
                [563, 1109, 1126],
            ),
            (
                "Comments MUST follow appropriate style and MUST NOT contain suspicious markers",
                [546],
            ),
        ],
        "Modifiability": [
            (
                "Code MUST NOT use obsolete, dangerous, or prohibited functions",
                [407, 474, 475, 477, 483, 676, 1177],
            ),
            (
                "Hard-coded literals and magic numbers MUST be replaced with symbolic constants",
                [1052, 1106, 1107],
            ),
            (
                "Global variables MUST NOT be used excessively; shared state MUST be minimized",
                [1108],
            ),
            (
                "Data representations MUST NOT be excessively complex or machine-dependent",
                [1093, 1101],
            ),
        ],
        "Reusability": [
            (
                "Serialization control elements MUST be properly implemented",
                [1066, 1070],
            ),
            (
                "Singleton classes MUST use proper locking and synchronization for instance creation",
                [1058, 1063, 1096],
            ),
            (
                "Data elements containing pointers MUST implement proper copy control",
                [1082, 1097, 1098],
            ),
        ],
        "Testability": [
            (
                "Input validation frameworks MUST be properly used",
                [1173],
            ),
            (
                "Compilation MUST enable sufficient warnings and errors",
                [1127],
            ),
            (
                "Code MUST NOT rely on self-modifying techniques",
                [1123],
            ),
            (
                "Database indices MUST NOT be excessive and queries MUST use efficient access patterns",
                [1072, 1089, 1094],
            ),
        ],
    },

    # ===================================================================
    # PERFORMANCE
    # ===================================================================
    "performance": {
        "Resource Utilisation": [
            (
                "Memory allocation MUST NOT use excessively large size values from untrusted input",
                [789],
            ),
        ],
        "Time Behaviour": [
            (
                "CPU computation MUST NOT be unnecessarily inefficient",
                [1176],
            ),
        ],
    },
}

# Prefix map: dimension → principle → id prefix
_PREFIX_MAP = {
    "security": {
        "Confidentiality": "S-CON",
        "Integrity": "S-INT",
        "Non-repudiation": "S-NRP",
        "Accountability": "S-ACC",
        "Authenticity": "S-AUT",
    },
    "reliability": {
        "Maturity": "R-MAT",
        "Availability": "R-AVA",
        "Fault Tolerance": "R-FT",
        "Recoverability": "R-REC",
    },
    "maintainability": {
        "Modularity": "M-MOD",
        "Reusability": "M-REU",
        "Analyzability": "M-ANA",
        "Modifiability": "M-MDF",
        "Testability": "M-TST",
    },
    "performance": {
        "Time Behaviour": "P-TIM",
        "Resource Utilisation": "P-RES",
        "Capacity": "P-CAP",
    },
    "usability": {},
    "flexibility": {},
}


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
    if dimension not in MAPPING:
        return 0

    filepath = STANDARDS_DIR / f"{dimension}.json"
    if not filepath.exists():
        print(f"  SKIP {dimension}: file not found")
        return 0

    data = json.loads(filepath.read_text())
    existing = _get_existing_cwes(data)
    prefixes = _PREFIX_MAP.get(dimension, {})
    total_added = 0

    for sc in data["sub_characteristics"]:
        sc_name = sc["name"]
        if sc_name not in MAPPING[dimension]:
            continue

        prefix = prefixes.get(sc_name, "X-XXX")
        highest = _get_highest_id(sc["requirements"], prefix)

        for req_text, cwe_ids in MAPPING[dimension][sc_name]:
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
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
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

    grand_total = 0
    for dimension in ["security", "reliability", "maintainability", "performance"]:
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
        print("\nRe-resolving practices...")
        subprocess.run([sys.executable, str(tools_dir / "resolve_practices.py"), "--all"], check=True)
        print("\nRunning gap report...")
        subprocess.run([sys.executable, str(tools_dir / "compile_standards.py"), "--gaps"], check=True)


if __name__ == "__main__":
    main()
