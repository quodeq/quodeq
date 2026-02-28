from pathlib import Path


def test_readme_mentions_codecompass_dashboard():
    text = Path("README.md").read_text()
    assert "codecompass dashboard" in text
