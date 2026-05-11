"""Flask routes for the finding verifier (Plan 3).

Three endpoints under `/api/evaluations/<eval_id>/`:
  - POST /verify/<dimension>/<finding_id>   - run the verifier; persist + return
  - GET  /verifications                     - list all verifications for the eval
  - GET  /verifications/<verification_id>   - fetch one with manifest + raw response
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify

from quodeq.verifier.service import FindingNotFound, VerifierService
from quodeq.verifier.storage import VerificationsStore


def register_routes_verifier(app: Flask, service: VerifierService) -> None:
    """Register the verifier blueprint on `app` with the given service."""

    @app.post("/api/evaluations/<eval_id>/verify/<dimension>/<finding_id>")
    def post_verify(eval_id: str, dimension: str, finding_id: str):
        try:
            sr = service.verify_finding(
                evaluation_id=eval_id,
                dimension=dimension,
                finding_id=finding_id,
            )
        except FindingNotFound as exc:
            return jsonify({"error": "finding_not_found", "detail": str(exc)}), 404
        return jsonify(
            {
                "verification_id": sr.verification_id,
                "verdict": sr.verdict.value,
                "confidence": sr.result.response.confidence,
                "evidence_summary": sr.result.response.evidence_summary,
                "model": sr.result.model,
                "elapsed_ms": sr.result.elapsed_ms,
                "checklist": _checklist_to_dict(sr),
                "findings": _findings_to_dict(sr),
                "consistency_warnings": list(sr.result.consistency_warnings),
            }
        )

    @app.get("/api/evaluations/<eval_id>/verifications")
    def list_verifications(eval_id: str):
        db_path = service.evaluations_root / eval_id / "verifications.db"
        if not db_path.exists():
            return jsonify({"verifications": []})
        store = VerificationsStore(db_path)
        try:
            rows = store.list_for_evaluation(eval_id)
        finally:
            store.close()
        return jsonify(
            {
                "verifications": [
                    {
                        "verification_id": r.verification_id,
                        "dimension": r.dimension,
                        "finding_id": r.finding_id,
                        "verdict": r.verdict.value,
                        "confidence": r.confidence,
                        "evidence_summary": r.evidence_summary,
                        "model": r.model,
                        "elapsed_ms": r.elapsed_ms,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows
                ]
            }
        )

    @app.get("/api/evaluations/<eval_id>/verifications/<verification_id>")
    def get_verification_detail(eval_id: str, verification_id: str):
        db_path = service.evaluations_root / eval_id / "verifications.db"
        if not db_path.exists():
            return jsonify({"error": "not_found"}), 404
        store = VerificationsStore(db_path)
        try:
            record = store.get(verification_id)
        finally:
            store.close()
        if record is None:
            return jsonify({"error": "not_found"}), 404

        audit_dir = service.evaluations_root / eval_id / "verifier" / verification_id
        manifest = _read_json_if_exists(audit_dir / "manifest.json")
        raw_response = _read_json_if_exists(audit_dir / "response.json")
        system_prompt = _read_text_if_exists(audit_dir / "prompt.system.txt")
        user_prompt = _read_text_if_exists(audit_dir / "prompt.user.txt")

        return jsonify(
            {
                "verification_id": verification_id,
                "evaluation_id": record.evaluation_id,
                "dimension": record.dimension,
                "finding_id": record.finding_id,
                "verdict": record.verdict.value,
                "confidence": record.confidence,
                "evidence_summary": record.evidence_summary,
                "model": record.model,
                "elapsed_ms": record.elapsed_ms,
                "created_at": record.created_at.isoformat(),
                "manifest": manifest,
                "raw_response": raw_response,
                "checklist": (raw_response or {}).get("checklist"),
                "findings": (raw_response or {}).get("findings"),
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )


def _checklist_to_dict(sr) -> dict[str, Any]:
    return {
        q: {"answer": a.answer, "cite": a.cite}
        for q, a in sr.result.response.checklist.items()
    }


def _findings_to_dict(sr) -> dict[str, Any]:
    f = sr.result.response.findings
    return {
        "default_implementation": {"value": f.default_implementation.value, "cite": f.default_implementation.cite},
        "override_mechanism": {"value": f.override_mechanism.value, "cite": f.override_mechanism.cite},
        "abstraction_in_use": {"value": f.abstraction_in_use.value, "cite": f.abstraction_in_use.cite},
    }


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
