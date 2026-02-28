from codecompass.evaluate.lib.progress import format_start, format_end


def test_progress_formats():
    assert "START" in format_start("phase")
    assert "END" in format_end("phase")
