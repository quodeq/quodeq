# Provenance-gate regression matrix (issue #641)

Fixtures for the critical-severity **provenance gate** (added in PR #636, verified
in #638). Each subdirectory is one case:

```
<case>/
  expected.json     # dimension, req, target line + construct, expected verdict
  repo/             # a minimal repo root; the source file lives under repo/src/...
```

`repo/` is passed as `assemble_api_prompt(repo_root=...)` so the source renders as a
production path (`src/...`, role = PROD), not a fixture (which would carry a
"tone down" label and confound the result).

## The matrix

| case | dimension | req | provenance | expectation |
|------|-----------|-----|------------|-------------|
| `internal_nav_breadcrumb`    | reliability | R-FT-2 | internal | not critical |
| `internal_grade_boundary_bar`| reliability | R-FT-2 | internal | not critical |
| `internal_use_project_scores`| reliability | R-FT-2 | internal | not critical |
| `internal_local_cache`       | security    | S-AUT-3| internal | not critical |
| `external_request_path`      | security    | S-AUT-3| external | stays critical |
| `external_cli_arg_open`      | security    | S-AUT-3| external | stays critical |
| `external_header_deref`      | reliability | R-FT-2 | external | stays critical |

## ⚠️ Do not "fix" the internal fixtures

The four `internal_*` source files are **verbatim from commit `a84ab6f8`** — the
exact code that run `fa56db32` rated `critical`, captured *before* the later
code-level guards (`_SAFE_KEY_RE` in `c0edcd6f`, `= {}` default args in `521f46c6`).
Keeping them guard-free preserves the exact construct that was flagged. Adding a
null check, default, or validation makes the fixture stop representing the FP.
`test_fixture_construct_anchored_at_target_line` pins the construct + line to catch
such drift.

The three `external_*` files are synthetic controls: the flagged value is genuinely
attacker-controlled (an HTTP field, a CLI arg, a response header). They must stay
`critical` — the guard that the gate does not over-relax.

## Running the live check

The behavioral test (`../test_provenance_gate_behavioral.py`) is `integration`-marked
and skipped unless a standard (non-mlx) `gemma4:26b` is reachable:

```
ollama serve &
ollama pull gemma4:26b
AI_MODEL=gemma4:26b uv run pytest \
    tests/analysis/test_provenance_gate_behavioral.py -v -m integration
```

The structural guards in `../test_prompt_provenance_gate.py` run in normal CI with
no model.
