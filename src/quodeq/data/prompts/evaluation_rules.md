## Look for

Bad patterns, vulnerabilities, anti-patterns. Missing error handling, validation, logging, retries, abstractions.

Report BOTH violations AND compliance. Scoring is a ratio. For every principle with violations, also look for compliant files.

Report each occurrence separately. 5 misplaced methods = 5 findings.

NOT a violation: literal inside a constant/enum definition; long function that only registers routes; duplicated test setup; code that IS the remediation for the issue; the flagged line or its neighbour already contains the guard (`escapeHtml`, `length` check, null guard, `try`/`catch`); algorithm-intrinsic complexity (force-directed layout, MST, per-frame trig); count equals limit (`max 5` is `> 5`, not `>= 5`).

## Evidence

Quote the specific problem expression in `snippet` — VERBATIM from the source, exact characters, no paraphrase. Set `end_line` so that `end_line - line + 1` equals the number of lines in `snippet`. Code must be visible in source.

DROP if you can only point to absence, imports, paths, or module layout (unless the requirement explicitly demands the missing code be present in this file).

DROP speculative concerns: "could", "might", "should consider".

## Severity

- **critical** — Exploitable vulnerability or production-breaking bug, demonstrable from code as-is. SQL injection with user input reaching raw query; hardcoded secret; auth bypass; data loss on a real path. Hardening gaps, defense-in-depth, hypotheticals → NOT critical.
- **major** — Real quality or security issue. Should be fixed. Not directly exploitable.
- **minor** — Real defect in the quoted code: style violation, measurable inefficiency, concrete improvement. NOT a fallback for findings that fail the higher bar.

Compliance uses the same scale to mark importance of what's done right.

## Test files

Test file → max severity `minor`. Never `critical`/`major` on tests, fixtures, mocks, or specs.

Test files contain `eval(x)`, secrets, path-traversal payloads on purpose. A real issue surfaces as `minor`; that's enough.

## Self-check (every finding, including minor)

1. **Evidence** — Quote the problem line. Only "missing"/"absent" → drop.
2. **Concrete** — State the problem in 1–3 sentences about the quoted code, and name the concrete impact (what breaks, who is affected, or what attack/failure it enables).
3. **No hedging** — No "could", "might", "may", "should consider", "if X were larger", "if async", "in a hot path". Describe what the line does wrong AS WRITTEN.
4. **Impact** — Name the observable consequence. "Could be slow under load" without a profile is speculation.

For `critical`/`major` also:

5. **Attack/failure** — Describe specific attack or failure this code enables as written. Hedge words → `minor` only if 1–4 hold; else drop.
6. **Reachable** — Production code path. Tests, examples, dev scaffolding are not `critical`.

**Decision**: 1–4 fail → DROP entirely. 5–6 fail → `minor` only if 1–4 hold, else drop. `minor` is not a fallback bucket.

Fewer sharper findings beats long reports padded with speculation.
