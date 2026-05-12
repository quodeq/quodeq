"""Canonical fixtures for the v8 empirical regression suite.

Each fixture mirrors a real finding in the Quodeq evaluation store. The
ground_truth verdict was hand-confirmed against the actual code (see
docs/superpowers/specs/2026-05-12-v8-verifier-design.md, section "Risks").

Editing this file changes the contract that gates prompt iteration. Don't
add cases without confirming ground truth with a human first.
"""

from __future__ import annotations

EMPIRICAL_FIXTURES = [
    {
        "id": "d3412c14",
        "label": "FilesystemActionProvider (substitutability)",
        "file": "src/quodeq/api/app.py",
        "line": 34,
        "title": "Platform-specific filesystem dependency",
        "reason": (
            "The default provider is hardcoded to use `FilesystemActionProvider`, "
            "which couples the application logic directly to the local filesystem "
            "and prevents easy switching to cloud storage without code modification."
        ),
        "snippet": "    from quodeq.services.filesystem import FilesystemActionProvider",
        "enclosing_role": "composition_root",
        "ground_truth": "false_positive",
        "context_before": 60,
        "context_after": 60,
    },
    {
        "id": "ef7fffdb",
        "label": "_ASVS_OUTPUT_DIR (hardcoded path)",
        "file": "src/quodeq/config/standards_fetcher.py",
        "line": 25,
        "title": "Hardcoded output directory",
        "reason": (
            "The output directory 'asvs' is hardcoded as a constant rather than "
            "being configurable."
        ),
        "snippet": '_ASVS_OUTPUT_DIR = "asvs"',
        "enclosing_role": "module",
        "ground_truth": "confirmed",
        "context_before": 15,
        "context_after": 50,
    },
    {
        "id": "76002d21",
        "label": "_CACHING_FETCHER_MAX (hardcoded numeric)",
        "file": "src/quodeq/data/fs/report_parser/_run_lookup.py",
        "line": 11,
        "title": "Hardcoded cache limit",
        "reason": (
            "The maximum cache size is hardcoded as a constant, preventing users "
            "from adjusting memory usage via configuration without modifying the "
            "source code."
        ),
        "snippet": "_CACHING_FETCHER_MAX = 100",
        "enclosing_role": "module",
        "ground_truth": "confirmed",
        "context_before": 10,
        "context_after": 40,
    },
    {
        "id": "3a7fcabe",
        "label": "rescore.py default eval dir (argparse override)",
        "file": "tools/rescore.py",
        "line": 10,
        "title": "Hardcoded default evaluation directory",
        "reason": (
            "The default directory for evaluations is hardcoded in the "
            "docstring/logic, which prevents easy reconfiguration without "
            "modifying the source code."
        ),
        "snippet": "    evaluations_dir = evaluations/",
        "enclosing_role": "module",
        "ground_truth": "false_positive",
        "context_before": 5,
        "context_after": 170,
    },
]
