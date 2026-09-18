"""Report and violation builders shared by the test_sarif* siblings."""


def _report(dimension, violations, **extra):
    return {"dimension": dimension, "violations": violations, "compliance": [], **extra}


def _violation(**kw):
    base = {
        "principle": "Fault Tolerance",
        "file": "app.py",
        "line": 58,
        "end_line": 59,
        "title": "Empty except swallows errors",
        "reason": "The bare except hides failures.",
        "snippet": "except:\n    pass",
        "severity": "major",
        "req": "R-FT-1",
        "req_refs": [{"label": "CWE-390", "url": "https://cwe.mitre.org/data/definitions/390.html"}],
    }
    base.update(kw)
    return base
