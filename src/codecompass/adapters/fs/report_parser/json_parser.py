from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codecompass.adapters.fs.report_parser.grades import build_totals


def parse_report_json(json_path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(json_path.read_text())
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    violations = [
        {
            "principle": v.get("principle"),
            "file": v.get("file"),
            "line": v.get("line"),
            "title": v.get("title"),
            "reason": v.get("reason"),
            "severity": v.get("severity", "minor"),
            "snippet": v.get("snippet"),
            **({"cwe": v["cwe"]} if v.get("cwe") else {}),
        }
        for v in data.get("violations", [])
    ]
    compliance = [
        {
            "principle": c.get("principle"),
            "file": c.get("file"),
            "line": c.get("line"),
            "title": c.get("title"),
            "reason": c.get("reason"),
            "snippet": c.get("snippet"),
            **({"cwe": c["cwe"]} if c.get("cwe") else {}),
        }
        for c in data.get("compliance", [])
    ]

    return {
        "dimension": data.get("dimension"),
        "overallScore": data.get("overallScore"),
        "overallGrade": data.get("overallGrade"),
        "principles": [
            {"name": p.get("name"), "score": p.get("score"), "grade": p.get("grade")}
            for p in data.get("principles", [])
        ],
        "detailPrinciples": [],
        "violations": violations,
        "compliance": compliance,
        "totals": build_totals(violations, compliance),
    }


def parse_evidence_file(evidence_path: Path) -> dict[str, Any]:
    dimension = evidence_path.name.replace("_evidence.json", "")
    try:
        data = json.loads(evidence_path.read_text())
    except OSError:
        data = {}
    except json.JSONDecodeError:
        data = {}
    return {
        "dimension": dimension,
        "sourceFileCount": data.get("source_file_count"),
        "date": data.get("date"),
        "discipline": data.get("discipline"),
    }


def parse_eval_from_json(json_path: Path, project: str, run_id: str, dimension: str) -> dict[str, Any] | None:
    try:
        data = json.loads(json_path.read_text())
    except OSError:
        return None
    except json.JSONDecodeError:
        return None

    principle_grades = [
        {
            "principle": p.get("name"),
            "score": p.get("score"),
            "grade": p.get("grade"),
            "isOverall": False,
        }
        for p in data.get("principles", [])
    ]
    principle_grades.append(
        {
            "principle": "Overall",
            "score": data.get("overallScore"),
            "grade": data.get("overallGrade"),
            "isOverall": True,
        }
    )

    principle_map: dict[str, Any] = {}
    for p in data.get("principles", []):
        name = p.get("name", "")
        principle_map[name] = {
            "name": name,
            "score": p.get("score"),
            "grade": p.get("grade"),
            "violations": [],
            "compliance": [],
            "justification": "",
            "recommendations": [],
            "metrics": None,
        }
    for v in data.get("violations", []):
        key = v.get("principle", "")
        if key not in principle_map:
            principle_map[key] = {"name": key, "score": None, "grade": None, "violations": [], "compliance": [], "justification": "", "recommendations": [], "metrics": None}
        f = v.get("file")
        line = v.get("line")
        vd = {
            "code": v.get("snippet", ""),
            "severity": v.get("severity", "minor"),
            "file": f"{f}:{line}" if f and line else f,
            "title": v.get("title", ""),
            "reason": v.get("reason", ""),
        }
        if v.get("cwe"):
            vd["cwe"] = v["cwe"]
        principle_map[key]["violations"].append(vd)
    for c in data.get("compliance", []):
        key = c.get("principle", "")
        if key not in principle_map:
            principle_map[key] = {"name": key, "score": None, "grade": None, "violations": [], "compliance": [], "justification": "", "recommendations": [], "metrics": None}
        principle_map[key]["compliance"].append(c.get("snippet") or c.get("reason") or "")

    return {
        "dimension": dimension,
        "runId": run_id,
        "project": project,
        "principleGrades": principle_grades,
        "principles": list(principle_map.values()),
        "violations": data.get("violations", []),
        "compliance": data.get("compliance", []),
        "priorityRemediation": {"critical": [], "major": [], "minor": []},
        "rawContent": None,
    }
