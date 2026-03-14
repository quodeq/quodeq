from pathlib import Path


def test_readme_mentions_quodeq_dashboard():
    readme = Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text()
    assert "quodeq dashboard" in text
