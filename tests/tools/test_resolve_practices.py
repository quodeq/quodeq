import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from resolve_practices import resolve_practice


def test_resolve_practice_enriches_cwe_and_standards():
    """resolve_practice replaces bare CWE int with {id, name} and adds standards."""
    compiled = {
        "maintainability": {
            "id": "maintainability",
            "principles": [{
                "name": "Analyzability",
                "cwes": [{
                    "id": 1080,
                    "name": "Source Code File with Excessive Number of Lines of Code",
                    "refs": [
                        {"source": "iso25010", "ref": "M-ANA-1", "title": "Source files MUST NOT exceed 300 lines"},
                        {"source": "cisq", "title": "Source files MUST NOT exceed language-appropriate line limits"}
                    ]
                }]
            }]
        }
    }

    practice = {
        "id": "py-005",
        "title": "Keep source files under 300 lines",
        "dimension": "maintainability",
        "principle": "Analyzability",
        "cwe": 1080,
        "severity": "medium",
        "bad": "# 500 lines",
        "good": "# 200 lines",
        "explanation": "Split large files"
    }

    resolved, warnings = resolve_practice(practice, compiled)

    assert resolved["cwe"] == {"id": 1080, "name": "Source Code File with Excessive Number of Lines of Code"}
    assert len(resolved["standards"]) == 2
    assert resolved["standards"][0]["source"] == "iso25010"
    assert resolved["principle"] == "Analyzability"
    assert resolved["bad"] == "# 500 lines"  # preserved
    assert len(warnings) == 0


def test_resolve_practice_warns_on_principle_mismatch():
    """Warning when practice declares principle X but CWE is under principle Y."""
    compiled = {
        "maintainability": {
            "id": "maintainability",
            "principles": [{
                "name": "Modularity",
                "cwes": [{"id": 1080, "name": "Excessive Lines", "refs": []}]
            }]
        }
    }

    practice = {
        "id": "py-005", "title": "...", "dimension": "maintainability",
        "principle": "Analyzability",  # wrong — CWE is under Modularity
        "cwe": 1080, "severity": "medium", "bad": "", "good": "", "explanation": ""
    }

    _, warnings = resolve_practice(practice, compiled)
    assert len(warnings) == 1
    assert "Analyzability" in warnings[0]
    assert "Modularity" in warnings[0]


def test_resolve_practice_warns_on_missing_cwe():
    """Warning when practice CWE is not in any compiled standard."""
    compiled = {
        "security": {
            "id": "security",
            "principles": [{"name": "Integrity", "cwes": []}]
        }
    }

    practice = {
        "id": "py-099", "title": "...", "dimension": "security",
        "principle": "Integrity", "cwe": 9999,
        "severity": "medium", "bad": "", "good": "", "explanation": ""
    }

    resolved, warnings = resolve_practice(practice, compiled)
    assert len(warnings) == 1
    assert "9999" in warnings[0]
    assert resolved["cwe"] == {"id": 9999, "name": "CWE-9999"}
    assert resolved["standards"] == []
