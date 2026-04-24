## What to look for

Look for TWO types of issues:
1. **What the code does wrong** — bad patterns, vulnerabilities, anti-patterns
2. **What the code is missing** — absent error handling, missing validation, no logging, no retry logic, missing abstractions

**Report BOTH violations AND compliance** — scoring uses the ratio between them. For every principle where you find violations, actively look for files that DO follow the standard and report compliance.

**Be thorough** — a single file can have multiple violations of the same requirement. Report each occurrence separately. For example, a class with 5 methods that don't belong = 5 separate findings, not 1.

**Avoid false positives** — a string/number literal inside a constant definition or enum is NOT a magic literal; a long function that only registers routes with no extractable logic is not always splittable; duplicated test setup code may be intentional. If the code IS the remediation for the issue, it is not a violation.

## Evidence requirement

Every violation must cite code that is directly visible in the provided source.

- Quote the specific expression, statement, or call that IS the problem in the `snippet` field.
- Do NOT infer violations from imports, function names, file paths, module layout, or the *absence* of code — unless a requirement explicitly demands that the missing code be present in this file.
- If you cannot point to a concrete line where the problem manifests, do not flag it.
- Speculative concerns ("this could be vulnerable to X", "this might allow Y", "should consider Z") are NOT violations. Only report issues you can prove from the code shown.

## Severity

For violations:
- **critical** — An exploitable vulnerability or production-breaking bug with clear, demonstrable impact visible in the code. Examples: SQL injection with user-controlled input reaching a raw query; hardcoded secret committed to source; authentication bypass; data loss on a code path that will execute in production. Do NOT use `critical` for missing best-practice controls, hardening gaps, defense-in-depth concerns, or hypothetical attack scenarios — those are `major` or `minor`. If you cannot describe a concrete attack or failure that this code enables right now, it is not critical.
- **major** — Significant quality issue or real security weakness that should be fixed, but not directly exploitable or production-breaking as-is.
- **minor** — Style issue, minor inefficiency, or improvement opportunity.

For compliance — use the same severity to indicate the importance of what's done right:
- **critical** — Security best practice correctly implemented, safe data handling
- **major** — Significant quality pattern properly followed
- **minor** — Good style, naming, or minor best practice followed

## Severity self-check

Before finalizing ANY violation, verify:

1. **Evidence**: Can you quote the exact line of code that IS the problem? If you can only point to what's *missing* or *absent*, drop the finding.
2. **Concreteness**: Can you state the problem in one specific sentence that refers to the quoted code? Vague concerns ("might not be safe", "could be improved") do not pass.

Additionally for `critical` and `major`:

3. **Attack/failure scenario**: Can you describe, in one sentence, a specific attack or failure this code enables *as written*? If your reasoning uses "could", "might", "may", or "should consider" — downgrade to `minor`.
4. **Reachability**: Does this code execute in a realistic production path? Code in test files, examples, or dev-only scaffolding is not `critical`.

If checks 1–2 fail, omit the finding. If checks 3–4 fail, downgrade to `minor` or omit. Being wrong on severity hurts the report more than missing a true positive at a lower severity.
