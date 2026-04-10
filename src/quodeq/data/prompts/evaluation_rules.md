## What to look for

Look for TWO types of issues:
1. **What the code does wrong** — bad patterns, vulnerabilities, anti-patterns
2. **What the code is missing** — absent error handling, missing validation, no logging, no retry logic, missing abstractions

**Report BOTH violations AND compliance** — scoring uses the ratio between them. For every principle where you find violations, actively look for files that DO follow the standard and report compliance.

**Be thorough** — a single file can have multiple violations of the same requirement. Report each occurrence separately. For example, a class with 5 methods that don't belong = 5 separate findings, not 1.

**Avoid false positives** — a string/number literal inside a constant definition or enum is NOT a magic literal; a long function that only registers routes with no extractable logic is not always splittable; duplicated test setup code may be intentional. If the code IS the remediation for the issue, it is not a violation.

## Severity

For violations:
- **critical** — Security vulnerability, data loss risk, or crash in production path
- **major** — Significant quality issue that should be fixed
- **minor** — Style issue, minor inefficiency, or improvement opportunity

For compliance — use the same severity to indicate the importance of what's done right:
- **critical** — Security best practice correctly implemented, safe data handling
- **major** — Significant quality pattern properly followed
- **minor** — Good style, naming, or minor best practice followed
