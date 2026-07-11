"""End-to-end: assistant dismiss draft -> apply -> finding actually suppressed.

Closes the coverage gap where only the DRAFT path was tested. The bug the user
hit lived entirely in the draft -> apply -> suppress leg: get_violations/
get_report never exposed the requirement, so a dismiss drafted from that data
carried a wrong/empty req that was durably recorded yet never matched the
finding on the suppression read path (silent no-op reporting dismissed: True).
"""
import json

from flask import Flask

from quodeq.assistant.tools import ToolContext, build_registry
from quodeq.assistant.tools._actions import ACTIONS
from quodeq.core.types.finding import Finding
from quodeq.data.sqlite.assistant_repository import AssistantRepository
from quodeq.services.dismissed import _finding_key, dismissed_keys


def _ctx(tmp_path, violations):
    eval_root = tmp_path / "evals"
    run_dir = eval_root / "proj" / "run1"
    (run_dir / "evaluation").mkdir(parents=True)
    (run_dir / "evaluation" / "security.json").write_text(json.dumps({
        "dimension": "security", "overallScore": 50, "overallGrade": "C",
        "principles": [], "violations": violations,
        "totals": {"violations": len(violations)},
    }))
    store = AssistantRepository(tmp_path / "assistant.db")
    store.create_session(session_id="s1", provider="ollama")
    ctx = ToolContext(
        repository=store, session_id="s1", run_dir=run_dir, repo_root=None,
        evaluators_dir=tmp_path / "e", compiled_dir=tmp_path / "c",
        dimensions_file=tmp_path / "d.json",
        project_id="proj", reports_dir=eval_root)
    return eval_root, ctx


def _app(eval_root):
    app = Flask(__name__)
    app.config["EVALUATIONS_DIR"] = str(eval_root)
    return app


def _apply_latest(ctx, eval_root, action_id):
    payload = ctx.repository.get_action(action_id)["payload"]
    return ACTIONS["dismiss_finding"].apply(payload, _app(eval_root))


def test_dismiss_roundtrip_suppresses_the_finding(tmp_path):
    eval_root, ctx = _ctx(tmp_path, [
        {"principle": "P1", "req": "R1", "file": "a.py", "line": 10,
         "severity": "critical", "title": "t", "reason": "r"}])
    reg = build_registry(ctx)

    # The model reads the finding; requirement is now exposed so it can key it.
    v = reg.dispatch("get_report", {"dimension": "security"})["result"]["violations"][0]
    assert v["requirement"] == "R1"

    draft = reg.dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": v["requirement"], "file": v["file"], "line": v["line"],
                    "reason": "guarded above"}})
    assert draft["ok"], draft
    result = _apply_latest(ctx, eval_root, draft["result"]["action_id"])
    assert result["dismissed"] is True

    # The dismissal is recorded AND its key matches the finding's own suppression
    # key, so the suppression read path actually drops it. Before the fix the
    # model had no way to obtain "R1" and would key on the principle, diverging.
    keys = dismissed_keys(eval_root / "proj")
    assert keys == {("R1", "a.py", 10)}
    finding = Finding(req="R1", file="a.py", line=10, practice_id="P1", severity="critical")
    assert _finding_key(finding) in keys


def test_dismiss_roundtrip_for_req_none_finding(tmp_path):
    # A finding whose canonical identity is only practiceId (req absent) must
    # also round-trip: exposed requirement is "", the draft accepts req="", and
    # the recorded key ("", file, line) matches the finding's ("", file, line).
    eval_root, ctx = _ctx(tmp_path, [
        {"principle": "P1", "file": "b.py", "line": 7,  # no req
         "severity": "major", "title": "t", "reason": "r"}])
    reg = build_registry(ctx)

    v = reg.dispatch("get_report", {"dimension": "security"})["result"]["violations"][0]
    assert v["requirement"] == ""

    draft = reg.dispatch("draft_action", {
        "action_type": "dismiss_finding",
        "payload": {"req": v["requirement"], "file": v["file"], "line": v["line"],
                    "reason": "not applicable here"}})
    assert draft["ok"], draft
    _apply_latest(ctx, eval_root, draft["result"]["action_id"])

    keys = dismissed_keys(eval_root / "proj")
    assert keys == {("", "b.py", 7)}
    finding = Finding(file="b.py", line=7, practice_id="P1", severity="major")  # req=None
    assert _finding_key(finding) in keys
