"""Tests for FindingsRouter enrichment and multi-dimension routing (split from test_mcp_findings)."""
from __future__ import annotations

import json
from pathlib import Path

from quodeq.analysis.mcp import findings_server as mcp_findings
from quodeq.analysis.mcp.findings_server import CompiledContext


class TestFindingsRouter:
    def test_enriches_req_refs_from_compiled(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {
            "S-CON-1": [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}],
        }
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, CompiledContext(compiled_refs=compiled_refs))
            msg, dup = router.receive({"p": "Confidentiality", "t": "violation", "d": "security", "w": "Hardcoded key", "req": "S-CON-1"})
        assert not dup
        assert "Finding #1" in msg
        written = json.loads(findings_file.read_text().strip())
        assert written["req_refs"] == [{"label": "CWE-798", "url": "https://cwe.mitre.org/data/definitions/798.html"}]

    def test_no_enrichment_without_matching_req(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        compiled_refs = {"S-CON-1": [{"label": "CWE-798", "url": "https://example.com"}]}
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh, CompiledContext(compiled_refs=compiled_refs))
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "UNKNOWN-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written

    def test_no_enrichment_without_compiled_refs(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({"p": "P1", "t": "violation", "d": "perf", "w": "Slow", "req": "S-CON-1"})
        written = json.loads(findings_file.read_text().strip())
        assert "req_refs" not in written

    def test_violation_on_test_file_gets_downweighted(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Slow", "file": "tests/test_server.py", "line": 10,
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["confidence"] == 50

    def test_violation_on_prod_path_keeps_full_confidence(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Slow", "file": "src/server.py", "line": 10,
            })
        written = json.loads(findings_file.read_text().strip())
        assert "confidence" not in written  # default 100 stays implicit

    def test_llm_emitted_low_confidence_is_preserved(self, tmp_path: Path) -> None:
        """If the LLM already lowered confidence, the path-role downweight
        does not overwrite it."""
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Slow", "file": "tests/test_server.py", "line": 10,
                "confidence": 25,
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["confidence"] == 25

    def test_compliance_finding_is_not_downweighted(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(fh)
            router.receive({
                "p": "P1", "t": "compliance", "d": "perf",
                "w": "OK", "file": "tests/test_server.py", "line": 10,
            })
        written = json.loads(findings_file.read_text().strip())
        assert "confidence" not in written

    def test_shape_downweights_hosted_service_finding_on_desktop_app(self, tmp_path: Path) -> None:
        from quodeq.context.project_shape import Deployment, ProjectShape
        findings_file = tmp_path / "findings.jsonl"
        shape = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(project_shape=shape),
            )
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Concurrent callers can corrupt shared state",
                "reason": "Multiple concurrent callers will race.",
                "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["confidence"] == 40

    def test_shape_does_not_downweight_unrelated_finding(self, tmp_path: Path) -> None:
        from quodeq.context.project_shape import Deployment, ProjectShape
        findings_file = tmp_path / "findings.jsonl"
        shape = ProjectShape(deployment=Deployment.DESKTOP, is_single_user=True)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(project_shape=shape),
            )
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Quadratic loop", "reason": "Nested for-loops over the same list.",
                "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        assert "confidence" not in written

    def test_precedent_match_downweights_to_25(self, tmp_path: Path) -> None:
        from quodeq.context.precedent import fingerprint
        findings_file = tmp_path / "findings.jsonl"
        snippet = "password = 'hunter2'"
        fp = fingerprint("S-CON-1", snippet)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(precedent_fingerprints={fp}),
            )
            router.receive({
                "p": "Confidentiality", "t": "violation", "d": "security",
                "req": "S-CON-1", "w": "Hardcoded credential",
                "snippet": snippet,
                "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["confidence"] == 25

    def test_precedent_miss_keeps_full_confidence(self, tmp_path: Path) -> None:
        findings_file = tmp_path / "findings.jsonl"
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(precedent_fingerprints={"some-other-fp"}),
            )
            router.receive({
                "p": "P1", "t": "violation", "d": "security",
                "req": "S-CON-1", "w": "Hardcoded credential",
                "snippet": "password = 'hunter2'",
                "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        assert "confidence" not in written

    def test_precedent_does_not_downweight_compliance(self, tmp_path: Path) -> None:
        from quodeq.context.precedent import fingerprint
        findings_file = tmp_path / "findings.jsonl"
        snippet = "password = 'hunter2'"
        fp = fingerprint("S-CON-1", snippet)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(precedent_fingerprints={fp}),
            )
            router.receive({
                "p": "P1", "t": "compliance", "d": "security",
                "req": "S-CON-1", "w": "OK",
                "snippet": snippet, "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        assert "confidence" not in written

    def test_precedent_respects_llm_emitted_confidence(self, tmp_path: Path) -> None:
        from quodeq.context.precedent import fingerprint
        findings_file = tmp_path / "findings.jsonl"
        snippet = "password = 'hunter2'"
        fp = fingerprint("S-CON-1", snippet)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(precedent_fingerprints={fp}),
            )
            router.receive({
                "p": "P1", "t": "violation", "d": "security",
                "req": "S-CON-1", "w": "Hardcoded credential",
                "snippet": snippet, "file": "src/main.py", "line": 5,
                "confidence": 60,
            })
        written = json.loads(findings_file.read_text().strip())
        assert written["confidence"] == 60

    def test_shape_does_not_downweight_for_web_service(self, tmp_path: Path) -> None:
        from quodeq.context.project_shape import Deployment, ProjectShape
        findings_file = tmp_path / "findings.jsonl"
        shape = ProjectShape(deployment=Deployment.WEB_SERVICE, is_single_user=False)
        with open(findings_file, "w") as fh:
            router = mcp_findings.FindingsRouter(
                fh, CompiledContext(project_shape=shape),
            )
            router.receive({
                "p": "P1", "t": "violation", "d": "perf",
                "w": "Concurrent callers can corrupt shared state",
                "reason": "Multiple concurrent callers will race.",
                "file": "src/main.py", "line": 5,
            })
        written = json.loads(findings_file.read_text().strip())
        # Web service: the hosted-service finding stays at full confidence.
        assert "confidence" not in written


class TestFindingsRouterMultiDimension:
    def test_derives_dimension_from_req_id(self):
        """In consolidated mode, dimension comes from req_to_dim mapping."""
        import io
        from quodeq.analysis.mcp.findings_server import FindingsRouter

        fh = io.StringIO()
        req_to_dim = {"S-CON-1": "security", "M-MOD-1": "maintainability"}
        reqs = {
            "S-CON-1": {"principle": "Confidentiality", "text": "..."},
            "M-MOD-1": {"principle": "Modularity", "text": "..."},
        }
        router = FindingsRouter(
            output_fh=fh,
            context=CompiledContext(compiled_reqs=reqs, req_to_dim=req_to_dim),
        )

        msg1, dup1 = router.receive({"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "w": "test"})
        msg2, dup2 = router.receive({"req": "M-MOD-1", "t": "violation", "file": "b.py", "line": 2, "w": "test2"})

        lines = [json.loads(l) for l in fh.getvalue().strip().split("\n")]
        assert lines[0]["d"] == "security"
        assert lines[1]["d"] == "maintainability"

    def test_fallback_to_single_dimension(self):
        """When req_to_dim is empty, falls back to self._dimension."""
        import io
        from quodeq.analysis.mcp.findings_server import FindingsRouter

        fh = io.StringIO()
        reqs = {"S-CON-1": {"principle": "Confidentiality", "text": "..."}}
        router = FindingsRouter(
            output_fh=fh,
            context=CompiledContext(compiled_reqs=reqs, dimension="security"),
        )

        router.receive({"req": "S-CON-1", "t": "violation", "file": "a.py", "line": 1, "w": "test"})

        line = json.loads(fh.getvalue().strip())
        assert line["d"] == "security"
