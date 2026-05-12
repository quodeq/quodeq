# Verifier (v8)

A finding-claim verifier. Given an evaluator's finding (file, line, title,
reason, snippet, context) and the surrounding source code, decides whether
the claim is substantiated.

## Output

JSON validated against `schema.py`:

```json
{
  "checklist": {
    "Q1": {"answer": "yes|no|unknown", "cite": "file:line or MANIFEST or null"},
    "Q2": {"answer": "...", "cite": "..."},
    "Q3": {"answer": "...", "cite": "..."},
    "Q4": {"answer": "...", "cite": "..."}
  },
  "confidence": 0.0,
  "evidence_summary": "..."
}
```

The model never picks a verdict. `verdict.py` computes it from `Q1`-`Q3`
(Q4 is advisory):

- `Q1=no` → `false_positive` (cited code doesn't match the claim)
- `Q2=yes ∧ Q3=yes` → `false_positive` (override mechanism exists)
- `Q1=yes ∧ Q2=no ∧ Q3=yes` → `confirmed` (claim stands)
- otherwise → `inconclusive`

## Prompt design

`SYSTEM_PROMPT_V8` is generic — it does not name any specific violation
category. The model uses the four checklist questions to evaluate any claim
against any evidence. A single concrete worked example (hardcoded retry
count) anchors the reasoning shape without prescribing categories.

Iterate the prompt against `tests/verifier/test_empirical.py` (opt-in via
`pytest -m empirical`). The 4 fixtures cover substitutability (with a
seam), no-seam path, no-seam numeric, and CLI argparse override — those
are the contract.

## Service layer

- `service.py` orchestrates: finding lookup → manifest build → source-context
  read → prompt render → Ollama call → citation validation → verdict.
- The manifest is built (`resolver.build_manifest`) but the prompt no longer
  consumes its fields — manifest is kept for the audit log only.
- Default source-context window: ±30 lines around the cited line.

## Errors

- `LLMUnreachableError` → HTTP 503 (`"error": "llm_unreachable"`).
- `VerifierTimeoutError` → HTTP 504.
- `MalformedResponseError` → HTTP 502.

## Backward compatibility

`Verdict.NOT_APPLICABLE` is retained in the enum so persisted v7.2 records
load. v8 never produces it.
