"""Regression: a single-dim run after a bundle run must reuse the bundle's fingerprint.

Reported 2026-05-06: `quodeq evaluate . --dimensions security` after a nightly
that ran 5 dimensions including security re-analyzed every file from scratch
instead of carrying forward the security_fingerprint.json the nightly wrote.
"""
from quodeq.analysis._types import AnalysisOptions


def test_analysis_options_incremental_defaults_true():
    """The internal incremental strategy flag defaults to True.

    A run that never explicitly opts out should carry-forward by default.
    """
    opts = AnalysisOptions()
    assert opts.incremental is True, (
        "Default-False causes single-dim re-runs to ignore prior bundle fingerprints. "
        "See docs/superpowers/plans/2026-05-06-incremental-by-default.md"
    )


def test_single_dim_reuses_bundle_fingerprint(tmp_path, monkeypatch):
    """A single-dim run after a bundle run reuses the bundle's fingerprint.

    This is the exact scenario the user reported on 2026-05-06: running
    `quodeq evaluate . --dimensions security` after a nightly that ran 5
    dimensions including security used to re-analyze every file from
    scratch. With incremental as the default, it should now find the
    nightly's security_fingerprint.json and carry findings forward.

    Directory layout mirrors what resolve_evidence_paths expects:
        <tmp_path>/<project_uuid>/<run_id>/evidence/
    list_runs additionally requires evidence/manifest.json to exist.
    """
    from quodeq.analysis.fingerprint import (
        build_fingerprint,
        find_previous_fingerprint,
        save_fingerprint,
    )

    # Simulate a bundle run that produced a security_fingerprint.json.
    # Path structure: <reports_base>/<project_uuid>/<run_id>/evidence/
    reports_base = tmp_path / "reports"
    project_uuid = "test-project-uuid"
    bundle_run_id = "2026-05-04T03-00-00-000Z"
    bundle_evidence = reports_base / project_uuid / bundle_run_id / "evidence"
    bundle_evidence.mkdir(parents=True)
    # list_runs requires manifest.json in the evidence folder.
    (bundle_evidence / "manifest.json").write_text("{}")

    # Source files for the fingerprint.
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("print('hi')")

    # Build and save the fingerprint as a real bundle run would.
    fp = build_fingerprint(
        src,
        ["app.py"],
        "security",
        standards_dir=None,
        analyzed_files={"app.py"},
    )
    save_fingerprint(fp, bundle_evidence)

    # Simulate a new single-dim run in a sibling run directory.
    new_run_id = "2026-05-06T10-00-00-000Z"
    new_evidence = reports_base / project_uuid / new_run_id / "evidence"
    new_evidence.mkdir(parents=True)
    (new_evidence / "manifest.json").write_text("{}")

    # find_previous_fingerprint must discover the bundle run's fingerprint.
    found_fp, found_dir = find_previous_fingerprint(new_evidence, "security")

    assert found_fp is not None, (
        "Single-dim run did not find the bundle's prior security fingerprint. "
        "This is the reported bug -- fingerprint discovery should be dimension-"
        "scoped but bundle-agnostic."
    )
    assert found_dir == bundle_evidence
    assert "app.py" in found_fp.get("file_hashes", {}), (
        "file_hashes missing expected file from bundle fingerprint"
    )
    # Verify the analyzed_files set is preserved across the run boundary.
    assert "app.py" in (found_fp.get("analyzed_files") or []), (
        "analyzed_files not carried forward from bundle fingerprint"
    )
