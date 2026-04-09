from quodeq.analysis.subagents._finding_classifier import classify_findings


def test_finding_in_queue_goes_to_inline():
    findings = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 1
    assert len(mini) == 0
    assert inline[0]["file"] == "a.py"


def test_finding_not_in_queue_goes_to_mini():
    findings = [
        {"file": "c.py", "p": "S", "t": "violation", "line": 1, "reason": "r"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 0
    assert len(mini) == 1
    assert mini[0]["file"] == "c.py"


def test_mixed_findings_split_correctly():
    findings = [
        {"file": "a.py", "p": "S", "t": "violation", "line": 1, "reason": "r1"},
        {"file": "c.py", "p": "S", "t": "violation", "line": 2, "reason": "r2"},
        {"file": "a.py", "p": "S", "t": "compliance", "line": 3, "reason": "r3"},
    ]
    queue_files = {"a.py", "b.py"}
    inline, mini = classify_findings(findings, queue_files)
    assert len(inline) == 2
    assert len(mini) == 1


def test_empty_findings():
    inline, mini = classify_findings([], {"a.py"})
    assert inline == []
    assert mini == []


def test_no_file_key_goes_to_mini():
    findings = [{"p": "S", "t": "violation", "line": 1, "reason": "r"}]
    inline, mini = classify_findings(findings, {"a.py"})
    assert len(inline) == 0
    assert len(mini) == 1
