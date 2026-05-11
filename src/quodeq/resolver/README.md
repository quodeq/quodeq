# quodeq.resolver

Symbol resolver and manifest builder. Powers the finding verifier by turning a
finding (file + line + category) into a structured manifest with cross-file
facts (where a symbol is defined, who inherits from it, who uses it as a
parameter type) and same-file shape signals (lazy imports inside functions,
`param or factory()` seams).

## Public API

```python
from quodeq.resolver import Resolver, FindingInput

resolver = Resolver(project_root=Path("/path/to/repo"))
resolver.build_index()  # scan-time, ~30s–5min depending on repo size

finding = FindingInput(file="src/api/app.py", line=34, category="adaptability")
manifest = resolver.build_manifest(finding)
manifest.to_dict()  # serialize for the verifier prompt
```

## Adding a new language

1. Implement a subclass of `LanguageAdapter` in `languages/<lang>.py`.
2. Add tree-sitter S-expression queries in `languages/queries/<lang>/`.
3. Register the adapter in `languages/__init__.py`.

The resolver code (`indexer.py`, `queries.py`, `manifest.py`) is language-
agnostic; only the adapter and its queries change per language.

## Architecture notes

- Tree-sitter only — no jedi, no language servers. Every query the verifier
  asks is structural (name lookup, base-list match, parameter annotation
  match), not type-theoretic.
- Symbol index lives in SQLite, built once per scan, reused across all
  evaluations and dimensions on that scan.
- Path role classifier marks composition roots (`app.py`, `main.py`, `cli.py`,
  `__main__.py`) so the verifier knows that concrete imports in those files
  are dependency-injection seams, not coupling violations.
