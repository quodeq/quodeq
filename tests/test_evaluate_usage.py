from codecompass.evaluate.lib.usage import evaluate_usage


def test_evaluate_usage():
    usage = evaluate_usage()
    assert "codecompass evaluate" in usage
    assert "-d/--dimensions" in usage
    assert "--plans-only" in usage
    assert "--no-prescan" in usage
    assert "--evidence-only" in usage
    assert "--numerical" in usage
    assert "--help" in usage
