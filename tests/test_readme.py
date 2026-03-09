from pathlib import Path


def test_readme_mentions_quodeq_dashboard():
    text = Path("README.md").read_text()
    assert "quodeq dashboard" in text
