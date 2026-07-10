# Final Review Fix Report — 2026-07-10

## Item 1 (Critical): parse CWEs from req_refs as well as refs

**Files changed:**
- `benchmarks/quodeq_bench/evidence.py` — `_finding_from_line`: replaced the single `tuple(str(r) for r in obj.get("refs", []))` expression with a two-step merge that first collects `refs` strings, then iterates `obj.get("req_refs", [])` and appends each dict's `"label"` value (when it is a `str`). The final `refs=tuple(refs)` feeds the unchanged Finding dataclass; `parse_cwe_refs` needed no modification.
- `tests/benchmarks/test_evidence.py` — added `test_req_refs_parsed_when_refs_absent`: builds a violation line with no `"refs"` key but `"req_refs": [{"label": "CWE-89", "url": "..."}, {"label": "OWASP-A03"}]`, loads it via `load_findings`, and asserts `"CWE-89" in findings[0].refs` and `parse_cwe_refs(findings[0].refs) == (89,)`.
- `tests/benchmarks/fixtures/replay/py-security/security_evidence.jsonl` — line 2 (command-injection / CWE-78) changed from `"refs": ["CWE-78"]` to `"refs": [], "req_refs": [{"label": "CWE-78"}]`. The e2e replay test still records recall/precision 0.75 unchanged.

## Item 2 (Critical): js-security SQLi/eval labels populated with reqs

**Files changed:**
- `benchmarks/corpus/synthetic/js-security/truth.json` — two label `"reqs"` arrays that were `[]` now contain requirement ids drawn from `src/quodeq/data/standards/iso25010/security.json`:

| Label | CWEs | req id chosen | Standard text (first 90 chars) |
|---|---|---|---|
| SQL injection via template literal (server.js:8) | 89, 564 | `S-INT-2` | "SQL queries MUST use parameterised statements; string concatenation is forbidden" |
| eval of user input (server.js:13) | 95, 94 | `S-AUT-1` | "Dynamic code evaluation (eval) MUST NOT be used with user-controlled input" |

Both ids were verified to exist in `security.json` and their texts directly cover the respective vulnerability patterns.

## Item 3 (Important): report meta completeness

**Files changed:**
- `benchmarks/quodeq_bench/report.py` — `collect_meta`:
  - Extended the existing `digest` to also hash files under `src/quodeq/data/standards/compiled` (same relative-path + bytes pattern; guarded by `if compiled_dir.is_dir()` so it silently skips when absent).
  - Added a separate `corpus_digest` (sha256) over all `benchmarks/corpus/synthetic/*/truth.json` files (sorted, relative-path + bytes); result stored as `"corpus_hash"` in the returned dict.
- `tests/benchmarks/test_report.py` — `test_collect_meta_in_repo` extended with `assert len(meta["corpus_hash"]) == 64`.

## Item 4 (Important): workflow permissions

**Files changed:**
- `.github/workflows/benchmark.yml` — added `permissions: contents: read` under the `gate:` job (before `runs-on:`), matching repo style for least-privilege workflows.

## Item 5 (Record correction): plan doc refs claim

**Files changed:**
- `docs/superpowers/plans/2026-07-10-accuracy-benchmark-harness.md` — Global Constraints line 19 amended: after `optional \`confidence\`` added `; enricher additionally attaches \`req_refs\` (list of \`{label, url}\` dicts) — the deterministic CWE carrier; harness parses both`. No other content changed.

## Test run

Command: `PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH" uv run pytest tests/benchmarks/ -q`

Output tail:
```
......................................................                   [100%]
54 passed in 0.48s
```
(53 pre-existing + 1 new `test_req_refs_parsed_when_refs_absent`)
