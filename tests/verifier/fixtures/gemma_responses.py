"""Canned Gemma 4 responses for the verifier integration tests.

Captured from `memory/project_enricher_fixture_di_default.md` (v7.2 clean run).
Used by the stub OllamaClient in conftest.py so integration tests run
deterministically in CI without requiring a live Ollama instance.
"""

DI_WITH_DEFAULT_FALSE_POSITIVE = {
    "checklist": {
        "Q1": {"answer": "yes", "cite": "MANIFEST"},
        "Q2": {"answer": "yes", "cite": "src/quodeq/api/app.py:34"},
        "Q3": {"answer": "yes", "cite": "MANIFEST"},
        "Q4": {"answer": "yes", "cite": "src/quodeq/services/filesystem.py:39"},
        "Q5": {"answer": "yes", "cite": "src/quodeq/api/app.py:90"},
    },
    "findings": {
        "default_implementation": {"value": "FilesystemActionProvider", "cite": "src/quodeq/api/app.py:36"},
        "override_mechanism": {"value": "param or factory()", "cite": "src/quodeq/api/app.py:90"},
        "abstraction_in_use": {"value": "ActionProvider", "cite": "src/quodeq/api/app.py:75"},
    },
    "confidence": 1.0,
    "evidence_summary": "The application initializes a default FilesystemActionProvider via _default_provider, but allows substitution by passing an ActionProvider instance to create_app.",
}


CONFIRMED_HARDCODED = {
    "checklist": {
        "Q1": {"answer": "yes", "cite": "MANIFEST"},
        "Q2": {"answer": "no", "cite": "src/some/file.py:10"},
        "Q3": {"answer": "no", "cite": None},
        "Q4": {"answer": "unknown", "cite": None},
        "Q5": {"answer": "no", "cite": None},
    },
    "findings": {
        "default_implementation": {"value": "ConcreteClass", "cite": "src/some/file.py:10"},
        "override_mechanism": {"value": None, "cite": None},
        "abstraction_in_use": {"value": None, "cite": None},
    },
    "confidence": 0.9,
    "evidence_summary": "ConcreteClass is instantiated at module scope with no DI seam.",
}
