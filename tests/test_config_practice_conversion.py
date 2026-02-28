from codecompass.config.practice_conversion import parse_practice_markdown


def test_parse_practice_markdown_extracts_metadata():
    markdown = """
# Example

## Metadata

| Field | Value |
|-------|-------|
| Discipline | backend |
| Topic | Example |
| Language | Python |
| Version | 1.0 |
| Scope | General |
| Enforcement Level | Advisory |
| Practices | 2 |
| Generated | 2026-02-25 |

## Practices Index

| ID | Practice | Section | Principle |
|----|----------|---------|----------|
| P01 | Do X | 1.1 | Principle |

---

## 1. Practice

Body text
"""
    result = parse_practice_markdown(markdown)
    assert result["metadata"]["discipline"] == "backend"
    assert result["metadata"]["practice_count"] == 2
