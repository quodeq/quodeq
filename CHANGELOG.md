# Changelog

## [0.6.0] — 2026-03-18

### Features
- **Redesigned scoring model** — base + lift + ceiling + floor system for more accurate quality grading (#93)
- **AI-powered fast pool** — replaced mechanical verification with intelligent subagent analysis (#94)
- **Universal multi-language analysis** — evaluate polyglot repos in a single run (#86)
- **Context rotation** — smarter token management for longer, deeper analysis sessions (#87)
- **Token usage reduction** — file-based standards, MCP auto-fill, leaner prompts (#91)
- **QuodeqBar** — macOS menu bar app to start/stop the dashboard and monitor evaluations (#82)
- **Server disconnect overlay** — dashboard shows connection status when the backend goes away (#82)
- **Dashboard favicon** (#82)

### Fixes
- Deferred verified findings until subagents complete (#aba161b)
- Project card shows accumulated grade instead of latest run only
- Heartbeat display fix + dead verify code cleanup (#88)
- 260+ auto-healed code quality violations across security, reliability, maintainability, performance, and flexibility (#90, #92, #95)
- 89 reliability violations resolved (#98, #99)
- 12 security violations resolved
- 7 integrity violations (CWE-345, CWE-353, CWE-20, CWE-601) (#97)
- 3 accountability violations (CWE-306, CWE-756) (#96)

---

## [0.5.0] — 2026-03-16

### Features
- **Severity-weighted compliance dampening** (8:4:1) — prevents minor compliance from offsetting critical violations
- **Post-analysis verification pass** — re-checks previous run's findings for consistency
- **Model override inputs** — configure main model + per-power-level analysis models in Settings
- **Analysis power selector** in Settings
- **Verify findings toggle** (On/Off)
- Subagent early exit when queue drains

### Security
- Localhost-only API access when no API key set
- Rate limiting on browse endpoint
- SSRF protection (private IP blocking, URL allowlists, path traversal validation)
- Sensitive env vars stripped from AI subprocess
- Cleartext HTTP blocked by default

### Fixes
- 150+ code quality violations resolved across 6 dimensions
- Wildcard imports eliminated, private re-exports cleaned up
- File splits for oversized modules

### CLI
- `--no-verify` flag and `QUODEQ_NO_VERIFY` env var

---

## [0.4.1] — 2026-03-14

### Features
- **Subagent pool** — parallel AI analysis with N agents, FileQueue-based file distribution
- **Power selector** — UI control for analysis depth (Haiku/Sonnet/Opus)
- **Distribution** — `pipx install quodeq` / `brew install quodeq/tap/quodeq`
- Centralized evaluations at `~/.quodeq/evaluations/`

### Security
- Path traversal validation, URL encoding, SSRF protection, stderr sanitization
- Single best CWE per finding instead of dumping all mapped refs

### Fixes
- Windows compatibility (fcntl → msvcrt, POSIX signals → Windows equivalents)
- Subagent stream/stderr cleanup after evidence extraction
- Retry logic, thread safety, narrowed exceptions

---

## [0.4.0] — 2026-03-14

Same as 0.4.1 — initial stable release of the v0.4 feature set.

---

## [0.2.0-alpha] — 2026-03-11

### Features
- Requirement-centric compiled format with ref badges
- Deduction-only scoring model

### Fixes
- Performance violations resolved across 16+ files
- Flexibility dimension violations (F-ADP, F-SCL, F-MOD, F-EXT)
- Accumulated view no longer hides stale dimensions
- Timezone-aware ISO date parsing

[0.6.0]: https://github.com/quodeq/quodeq/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/quodeq/quodeq/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/quodeq/quodeq/compare/0.4.0...v0.4.1
[0.4.0]: https://github.com/quodeq/quodeq/compare/0.2.0-alpha...0.4.0
[0.2.0-alpha]: https://github.com/quodeq/quodeq/compare/alpha-0.11.0...0.2.0-alpha
