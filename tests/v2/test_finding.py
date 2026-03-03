from codecompass.v2.engine.finding import Finding


def test_finding_required_fields():
    f = Finding(
        rule="eval-usage",
        label="Dynamic code evaluation",
        file="src/api/route.ts",
        dimension="security",
        detector="grep",
    )
    assert f.rule == "eval-usage"
    assert f.cwe is None
    assert f.severity_hint == "medium"


def test_finding_with_all_fields():
    f = Finding(
        rule="eval-usage",
        label="Dynamic code evaluation",
        file="src/api/route.ts",
        dimension="security",
        detector="grep",
        cwe=95,
        line=47,
        snippet="eval(userInput)",
        severity_hint="high",
    )
    assert f.cwe == 95
    assert f.line == 47
