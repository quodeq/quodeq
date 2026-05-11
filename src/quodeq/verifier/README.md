# quodeq.verifier

Verifier core. Turns a `quodeq.resolver` manifest into a structured verdict
(`false_positive` | `confirmed` | `inconclusive`) by rendering the v7.2 prompt,
calling a local LLM (Ollama/Gemma) with strict JSON-schema enforcement,
validating citations against the prompt's evidence, and computing the verdict
in Python from the checklist answers.

## Public API

```python
from quodeq.resolver import Resolver, FindingInput
from quodeq.verifier import Verifier, Verdict

resolver = Resolver(project_root=Path("/path/to/repo"))
resolver.build_index()
finding = FindingInput(file="src/api/app.py", line=34, category="adaptability")
manifest = resolver.build_manifest(finding)

verifier = Verifier(model="gemma:4")
result = verifier.verify(manifest, finding)
# result.verdict is a Verdict enum
# result.response carries the structured checklist + findings extraction
# result.consistency_warnings flags any model contradictions
# result.elapsed_ms records wall-clock time
```

## Architecture

- **Prompt:** the v7.2 template is a module-level constant (cached by Ollama).
  The per-finding user prompt is rendered from a `Manifest` by `prompt.py`.
- **Model call:** `OllamaClient` uses Ollama's `format=<json-schema>` parameter
  so the model is constrained to emit a valid JSON object matching the
  response schema. There is no streaming and no async (Plan 2 is synchronous).
- **Validation:** `enforce_citation_validity` downgrades any answer whose
  citation doesn't resolve to a visible `L<N>` line or `MANIFEST` to `unknown`.
  `self_consistency_warnings` flags contradictions between the structured
  `findings` extraction and the checklist.
- **Verdict:** computed in Python from Q3∧Q4∧Q5. The model never produces a
  verdict; this is the load-bearing reliability mechanism.

## Configuration

`Verifier(model="gemma:4", temperature=0.2)` are the defaults. Pass a custom
`OllamaClient` to override the base URL or timeout. For tests, inject a stub
client (see `tests/verifier/conftest.py`).

## Eval harness

`quodeq.verifier.eval_harness` exposes `load_eval_cases(directory)` and
`replay_case(case)`. Each `EvalCase` pins a canned model response and an
expected verdict; the harness recomputes the verdict and compares. Use to
regression-test the verdict rule and citation validator against historical
runs.
