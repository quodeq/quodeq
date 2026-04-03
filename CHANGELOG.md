# Changelog

## [0.10.0] — 2026-04-03

### Features
- **Map tab** — visual codebase health explorer with Heat Grid, Risk Matrix, and Circle Pack visualizations; drill-down navigation with breadcrumb; Violations/Health view toggle; dimension filter from visible standards
- **Single-file evaluation** — evaluate individual files from the Local browser; auto-detects parent project by git root; per-dimension analysis for deeper coverage
- **Finding dismissal** — dismiss false-positive violations with restore support; redesigned dismissed findings cards with full violation detail
- **Report copy button** — copy markdown report to clipboard from overview and dimension detail pages
- **Live rescore on dismiss** — accumulated scores update immediately when findings are dismissed
- **Online re-evaluation** — re-evaluate remote projects and clone-to-local from the dashboard

### Improvements
- Smooth fade transitions on tab switches, loading states, and run navigation
- Fix stale data flash when switching runs in history tab
- Project header shown on Violations and History tabs
- Backend clean architecture refactoring — all 8 phases

### Fixes
- Standard tree not showing principles after PrinciplesList extraction
- Redesigned fix plan and dismiss buttons across UI

### Code Quality
- 150+ maintainability violations resolved (rounds 3–7)

## [0.9.0] — 2026-04-01

### Features
- **Standards visibility toggle** — show/hide standards in the dashboard, bundled evaluators
- **Evaluator import/export** — import/export evaluators with validation and security scanning
- **History tab** — evaluation run list with run navigator and daily grouping
- **Overview daily grouping** — chart and navigator step by day with dimension highlights
- **Fingerprint-aware verification** — skip AI for unchanged files
- **Progressive coverage** — backfill unevaluated files across incremental runs
- **Theme system redesign** — family+mode architecture
- **UI redesign** — panels, cards, charts, settings, and project header overhaul

### Fixes
- Incremental flow fixes and dashboard --dev flag
- Backfill efficiency — accurate analyzed_files + skip verification
- Right-size verification pool agent count
- Save fingerprint after subagent analysis for carry-forward
- Raise default max export size from 100MB to 500MB
- Blank screen when switching between parent/child projects

### Code Quality
- 500+ maintainability violations resolved across analyzability, modularity, reusability, modifiability
- 10 security violations resolved
- Deleted deprecated re-export shims, extracted magic numbers, added docstrings to public APIs
- Reduced function fan-out, nesting depth, and parameter counts across codebase

## [0.8.1] — 2026-03-27

### Fixes
- Collapsible code blocks with minimal link style
- Decouple history run selection from overview
- Scope bar shows available snippet/context data from old evaluations
- Clickable bar for scope findings with compact accordion style
- VS Code-style line numbers in code context blocks
- See more/less toggle for large code blocks
- Cap code snippets in fix plans to 5 lines

### Code Quality
- 26 clean-architecture violations resolved

## [0.8.0] — 2026-03-26

### Features
- **Dashboard redesign** — golden-split hero panels with SVG ScoreCircle gauge, divided-row stats, grade-colored dimension cards
- **Horizontal bar charts** — pure CSS DimensionScorePanel replacing recharts, sorted alphabetically
- **Score history K4b** — thin bars + area line with gradient fill, selected dot indicator
- **Project header** — Q5 numbers-first layout with per-language file counts from manifest
- **Project cards R3** — two-row dense layout with language stats and grade colors
- **Settings two-column** — Analysis left, Appearance + About right, rotating tips in header
- **Breadcrumb pills** — M2 pill segments with accent-tinted active state
- **Loading screen** — pulsing Q logo replacing text loading states
- **Language stats** — surface language breakdown from manifest.json in project listings
- **Date format** — "22 Mar 2026" across server and UI

### Improvements
- Consolidated `EXT_NAMES`, `scoreGradeColorVar`, `GRADE_WORD_TO_LETTER` into formatters.js
- Cached `cssVar()` calls with MutationObserver for theme-change invalidation
- DimensionCardsGrid sort wrapped in useMemo
- Exponential backoff with jitter for health polling and dimension polling
- Retry with backoff in FetchClient and hybrid_call before circuit breaker/fallback
- Thread-safe LRU cache with per-key inflight coordination
- Protected menubar shared state with consistent lock usage

### Bug Fixes
- Fix hero delta using trend data source (consistent with bar chart)
- Fix ViolationsPage stats grid after CSS class removal
- Fix chart colors not updating on theme switch
- Clean up stderr temp file on all dashboard start paths

## [0.7.0] — 2026-03-23

### Features
- **Incremental analysis** — fingerprint-based change detection with dependency cascade; only re-analyzes changed files and their dependents
- **Progressive coverage** — each re-scan backfills previously-unevaluated files with remaining budget, gradually reaching full coverage
- **File prioritization** — 5-layer scoring (path patterns, dimension relevance, import fan-in, git churn, previous violations) ensures the most important files are analyzed first
- **Adaptive agent scaling** — scout-then-scale pool strategy adjusts agent count based on project size
- **Consolidated evaluation** — analyze multiple dimensions in a single pass, reducing token usage
- **Verify findings on by default** — fast verification pool enabled for all evaluations

### Fixes
- Server disconnected overlay only shows on evaluate screen; sidebar remains navigable
- Re-scan button now visible when fingerprints exist
- 156 auto-healed code quality violations across all dimensions

---

## [0.6.2] — 2026-03-22

### Features
- **On-demand UI build** — dashboard builds from source at runtime, eliminating stale static assets
- **Prerequisite checks** — `quodeq dashboard` validates Node.js 18+ and npm 9+; `quodeq evaluate` validates Claude Code
- **UI source in package** — moved from `ui/web/` to `src/quodeq/ui/`, ships inside the wheel
- **Content hash rebuilds** — SHA-256 hash detects source changes, skips unnecessary rebuilds
- **Homebrew-compatible** — no bundled static files; formula can `depends_on "node"`

---

## [0.6.1] — 2026-03-18

### Fixes
- **QuodeqBar** — correct port range (4173+), prereq checks on main thread, CLI flag detection
- **QuodeqBar** — alert on missing quodeq, invalidate command cache on Start, log stderr
- **Dashboard** — clicking a project on the Projects page now navigates to the overview

---

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

[0.9.0]: https://github.com/quodeq/quodeq/compare/v0.8.1...v0.9.0
[0.8.1]: https://github.com/quodeq/quodeq/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/quodeq/quodeq/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/quodeq/quodeq/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/quodeq/quodeq/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/quodeq/quodeq/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/quodeq/quodeq/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/quodeq/quodeq/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/quodeq/quodeq/compare/0.4.0...v0.4.1
[0.4.0]: https://github.com/quodeq/quodeq/compare/0.2.0-alpha...0.4.0
[0.2.0-alpha]: https://github.com/quodeq/quodeq/compare/alpha-0.11.0...0.2.0-alpha
