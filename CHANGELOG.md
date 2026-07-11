# Changelog

## [1.6.0] - 2026-07-11

### Features
- **AI Assistant**: a new chat drawer that understands your project. Ask about scores, principles, and specific violations without switching tabs; it reads the current overview run and the accumulated per-dimension view by default and answers in context. It runs on your analysis provider by default, or a provider you pick (cloud API or a local model, including Claude, Codex, and Gemini via their CLIs), and streams its replies. A welcome panel offers context-aware suggestion pills, and slash commands surface built-in skills. The Assistant is off until you toggle it on the first time, then on by default.
- **Assistant web access**: an optional globe toggle lets the Assistant search the web and fetch pages while it answers, off by default and per conversation. Native web tools are used when the provider supports them; otherwise a built-in DuckDuckGo search and an SSRF-guarded fetch (no redirects, size-capped, hostile-charset safe) stand in.
- **Assistant can dismiss, verify, and fix findings**: from the chat you can dismiss or verify a finding, and verified findings get a badge across the violation cards, the file drill-in, and the dashboard. With repo write access granted, the Assistant drafts changes in a jailed git worktree and you review them in a diff panel before choosing Apply, open a PR, or Discard. Nothing touches your working tree without that explicit gate.
- **Embedded terminal**: a bottom drawer hosts a real terminal (and the Assistant) in tabs, backed by a PTY on macOS and Linux and ConPTY on Windows. Open it from the topbar or with Ctrl+backtick, run multiple tabs, and maximize or hide the drawer. It is gated to localhost with an origin check, and can be enabled or disabled in Settings. Terminal and Assistant are enabled by default.
- **Editable standard thresholds**: managed standards now expose their numeric thresholds (inheritance depth, file length, and similar) as per-project overrides you can edit in the requirement form. A customized-thresholds badge marks standards you have tuned, resolved values show in the standard tree, and the overrides flow through prompts, findings, and scoring so a run reflects exactly the limits you set.
- **Benchmark harness**: a new `quodeq-bench` toolset with a labeled corpus across all quality dimensions, a case runner (subprocess or replay), per-dimension metrics, markdown reports, and a baseline-comparison regression gate wired into CI, so changes to analysis quality are measured instead of guessed.
- **Repo-local ignore rules**: a `.quodeqignore` file in the scanned repo excludes paths from analysis, and `detection.json` skip patterns are honored by the manifest walkers.

### Improvements
- **Period-aware dashboard trends**: the Overview dimension cards, sparklines, and deltas now respect the day/week/month grouping you choose, and the dimension-detail history uses the same grouping preference. Dimension card positions stay fixed as you change the period, and cards keep dimensions whose latest valid run is older than the window instead of dropping them. The project card grade now averages every dimension that has data.
- **Instant run-detail and lighter payloads**: opening a run is now near-instant thanks to hover prefetch (dwell-gated so it never storms the server) and a skeleton view, and run-detail responses were slimmed dramatically with gzip on large JSON. A per-project accumulated summary cache makes the project card render instantly when warm, and a new runs endpoint serves run lists as a compact unit with ETag conditional responses.
- **Excluded-file visibility**: the live-scan coverage header now shows how many files were excluded by the API file-size cap, and the cap is enforced at enumeration so coverage math is honest instead of silently topping out below 100%.
- **Faster, size-budgeted API dispatch**: files sent to API providers are grouped into size-budgeted sub-batches for more efficient dispatch.

### Fixes
- **Windows portability**: assistant edits preserve file bytes exactly (CRLF safe), text I/O is pinned to UTF-8 across subprocess and file handles, and process-tree kills work cross-platform. Several tests were made Windows-portable.
- **Terminal robustness**: multi-byte glyphs no longer tear during TUI redraws (an incremental UTF-8 decoder per session), a dropped socket now shows a reconnect overlay and recovers, and PTY size syncs to the terminal on open so full-screen TUIs are not clipped.
- **Scoring consistency**: dismiss and delete rescoring is now applied on every per-run read path, on the project-card grade, and through the Assistant's own read tools, so a dismissed finding reads the same everywhere. Accumulated and card grades are scoped to the latest run's configured dimensions.
- **Dashboard resilience**: a cold Overview load no longer blanks (it holds the loading screen until scores resolve and grace-falls-back otherwise), a React crash from hooks below an early return is fixed, run-detail no longer flickers, and the score cache no longer strands a run's partial in-progress dimensions.
- **Lifecycle**: SIGTERM races in run status handling were eliminated, and cleanup never removes the system temp root.

## [1.5.2] - 2026-07-03

### Improvements
- **In-app Help refreshed for the 1.3-1.5 features**: the Help screen now documents the Grade Formula editor, score history grouping, the omlx and llama.cpp local providers, and update notifications, illustrated with theme-paired screenshots throughout. The Violations help matches the real sub-tabs and the provider list is complete.
- **Adaptive Settings layout**: the Settings screen flows its option groups into as many columns as the window width allows (CSS grid lanes with a multi-column fallback) instead of a single fixed column.
- **Theme-reactive views**: dark-mode detection moved to a shared reactive hook, so the map and other visualizations repaint immediately when you switch between light and dark themes.

### Fixes
- **Elastic overscroll confined to content**: on macOS the rubber-band scroll is now limited to the content area, so the topbar and sidebar stay fixed instead of bouncing with the whole window.
- **Grade-formula boundaries hint**: the hint now mentions the arrow-key path for nudging grade boundaries, matching the keyboard support already in place.
- **Plain punctuation in the UI**: em-dashes were removed from user-facing strings.

## [1.5.1] - 2026-07-01

### Fixes
- **Close button no longer freezes the app during a scan**: closing the desktop window while an evaluation was running could hang the app ("stays loading"), a regression introduced with the native close confirmation in 1.5.0. The confirmation now runs off the GUI thread so it can no longer deadlock, and is shown inline on Windows where the native dialog is not marshaled, so the window closes cleanly and the scan keeps running in the background.
- **Restored the "Cancel scan and quit" option**: closing during a scan on macOS again offers three choices (Quit and keep scanning / Cancel scan and quit / Stay) instead of two, so you can stop a running scan as you quit. The safe "Stay" is the default. Windows and Linux keep the two-button dialog.

## [1.5.0] - 2026-07-01

### Features
- **Update notifications**: Quodeq now checks whether a newer version is available (via PyPI and GitHub) and surfaces it unobtrusively. A dismissible banner appears in the dashboard, Settings gains an Updates section, the CLI prints a one-line notice after commands, and the macOS menubar app gets a "Check for Updates" item. All checks are fail-silent and can be turned off, with a first-run disclosure explaining what is sent.
- **SARIF export**: emit findings as SARIF 2.1.0 for GitHub code scanning, GitLab, and other tools. Run `quodeq export sarif` on a completed run, or pass `--sarif` to `evaluate` to write it right after a scan. Snippets are off by default (opt in with `--with-snippets`), absolute host paths are never leaked, and emission is fail-soft so it can't turn a finished run into a failed one. The README documents a GitHub Actions snippet.
- **Score history grouping**: the overview score-history chart can be grouped by day, week, or month with a new granularity selector. The choice persists across sessions and the tooltip shows the period label.

### Improvements
- **Much faster dashboard launch**: a dedicated on-disk score cache plus a scalar fast-path make opening a dismissal-heavy project roughly 10x faster (sub-second when warm), with byte-identical scores. The cache invalidates on any change to dismissals, deletions, or the grade formula, rebuilds itself if corrupted, and has a kill switch.
- **Unified macOS titlebar**: the macOS window uses a frameless titlebar, with the dashboard topbar running to the top edge and the native traffic lights floating, vertically centered, over it. The topbar and sidebar share one plain surface color, and in fullscreen the titlebar is dropped so content fills the screen cleanly and restored on exit. Windows and Linux keep native OS chrome with a titlebar that follows the theme.
- **Accessibility**: full keyboard navigation for the galaxy canvas and the run/dimension history charts. Focus rings are now gated behind `:focus-visible` app-wide, so a stray border no longer appears on click in the desktop app.
- **Sharper analysis quality**: a finding's requirement is now authoritative for its dimension, so misfiled findings are rerouted instead of appearing under the wrong principle (this also retired the phantom "N/A" principle card). Provenance downgrades are tracked as a first-class field and surfaced in the dashboard, and dimensions killed by the failure-streak breaker are excluded from the projected grade and accumulated summary.
- **More resilient scans**: when the circuit breaker trips it salvages the partial evidence already gathered instead of discarding it, and the dimension loop stops promptly on cancellation. The default grade formula now matches the tuned preset.
- **Performance and dependencies**: the subagent scout timeout is lowered to 30s, and Python and dashboard dependencies were refreshed.

### Fixes
- **Dashboard window controls and the in-app bridge**: the desktop window has working native close/minimize/maximize controls again. The strict CSP shipped in 1.4.0 had disabled the injected macOS controls, and, because pywebview builds its JS bridge with `new Function`, also broke the in-app `save_file` (Standards export) and `download_url` (project ZIP) actions; both are restored by serving the relaxed CSP only to the native webview. Closing during a scan now shows a native confirmation dialog and the scan keeps running in the background.
- **Robustness**: JSON reads now enforce their dict contract, killing a recurring crash class where non-dict JSON hit `.get()`; malformed standards, req-mapping, and config files are tolerated rather than fatal; the grade projector is guarded against non-dict input; and external-link opening is scheme-checked.
- **UI polish**: the overview refetches when an evaluation finishes so it never shows stale scores; tab headers are consistent with a persistent project indicator; server status moved to a compact toolbar dot; the nav count shows a compact "k" instead of a hard 999+ cap; score history gains dotted 0%/100% gridlines; and the decorative arrow before the project name is gone.

## [1.4.0] - 2026-06-20

### Features
- **Finding taxonomy**: analysis now emits taxonomy codes so fresh runs group findings by their vulnerability taxonomy, not just by principle (PRs #622, #623, #624).

### Improvements
- **Analysis quality**: critical severity now requires reachable input provenance, sharply cutting false-positive criticals. New coverage and import-layer baseline gates keep quality from regressing (PRs #623, #636).
- **Accessibility**: keyboard navigation across the map and galaxy visualizations, grade-boundary sliders, and resizable side-pane dividers; the evaluation error toast is now a proper button (PR #643).
- **Performance**: heavy scoring and projection work moved off the request thread, an N+1 query batched into one, and rate-limit state is now bounded (PR #643).
- **Resilience**: the dimension list is recovered from sidecars when run status is missing (PR #627); a downgraded `~/.quodeq/index.db` is discarded and rebuilt from the run files instead of crashing on first access (#621); more API errors carry machine-readable codes (PR #643).
- **Configuration**: cache paths, dimensions, and provider settings are no longer hardcoded (PR #643).

### Fixes
- **Security**: a broad hardening pass - a Windows command-injection guard, an atomic no-follow rate-limit file write, path-traversal containment (cache keys, run-events job ids, custom-evaluator ids, cache hashing), SSRF guards on the omlx and project-clone paths (including git@ SSH and encoded-IPv4 bypasses), a tightened Content-Security-Policy, and a localhost-only webview reload allowlist (PRs #629, #642, #643, #644, #646).
- **Reliability**: timeouts on all external HTTP and SSE calls, consistent exception handling, guards against malformed and non-dict input, atomic grade rewrites with concurrency locks, structured route error handling, and several UI crash guards including the galaxy view (PRs #634, #637, #646).
- **Scoring**: stop dropping untagged violations under partial taxonomy coverage, and emit taxonomy codes in production so grouping works on real runs (PRs #624, #628).

## [1.3.0] - 2026-06-11

### Features
- **Grade Formula Editor**: new Settings screen to tune how grades are computed. Adjust severity weights and grade boundaries on a live curve, preview the effect against recent runs, then apply to all runs with one click. Run detail, accumulated overview, trend and project cards all reflect the applied formula consistently (PRs #611, #614).
- **Evaluation progress**: the progress strip now ticks elapsed time every second and shows live throughput (files/min) with an estimated time remaining (PR #607).
- **API runner observability**: each run logs an aggregate parse summary (kept vs dropped findings) and raises a single warning when more than 5% of parsed findings were dropped, so a systemic model output problem is one signal instead of thousands of scattered log lines (PR #615).

### Improvements
- **Dashboard dependencies**: React 19.2.7 lockstep restored, TanStack Query/Virtual refreshed, Vite/Vitest toolchain updated.

### Fixes
- **Evaluation progress**: no longer sticks at 97% when an evaluation finishes between polls (PR #609); elapsed ticking stays even and the throughput window survives screen re-entry (PR #608).
- **Dashboard**: clickable stat cards no longer render invalid nested buttons (PR #610).
- **Homebrew**: the tap formula now pins the published release commit instead of the develop branch head, so brew installs are reproducible.

## [1.2.0] - 2026-06-04

### Features
- **Event-sourced findings pipeline**: each run now appends judgments to an `events.jsonl` log as the durable truth, and SQLite is rebuilt from it as a derived projection (kept in sync during active runs via incremental ticks). User actions (dismiss, restore, delete) are recorded in an append-only `actions.jsonl`, so dismissals are replayable and never silently lost.
- **omlx local provider**: select omlx in the provider tabs alongside Ollama and llama.cpp on macOS Apple Silicon. Lists models from your local omlx server, with API key and server-address settings in an Advanced block, and falls back to a text input when the model list is empty.
- **Permissive content-addressed cache**: the result cache now invalidates only on a real per-file change (content, path, dimension, language). Switching model, updating Quodeq, or running a single dimension reuses cached findings with no re-dispatch. Force a fresh scan on demand with `--clean-scan`.
- **No Node.js or npm needed for installs**: the wheel now ships the pre-built dashboard under `quodeq/static/` and serves it directly. Production installs no longer pull or run npm. The `--dev` path still rebuilds from source for contributors.
- **Synchronous per-file cache writes**: findings are written to cache the moment a file finishes cleanly, on both the CLI and API paths, so a hard crash mid-run keeps every completed file instead of losing in-flight work.
- **Per-dimension exit reason**: each dimension records why it stopped (complete, deadline, failure streak, cancelled). The report and dashboard surface it per dimension, falling back to the run-level reason, and a partial dimension shows an amber coverage percentage on both the report card and the in-progress page.
- **Provider and model on the in-progress card**: the running-evaluation card shows the job's own provider and model in a chip, and external and CLI-started runs persist `ai_provider`/`ai_model` in `status.json` so the dashboard reflects what actually ran.
- **Mutation returns the new score**: dismissing, restoring, or deleting a finding returns the rescored run in the same response, so the displayed score updates in about a second with no refetch. Works on old runs that pre-date the event log via a JSON-file rescore fallback.

### Improvements
- **Windows is now a blocking test tier**: UTF-8 is forced on stdout, stderr, and every text I/O path at the CLI and API entry points, with a regression guard against non-UTF-8 file opens. Windows joins the integration lane with a packaged-exe boot smoke against `/api/health`.
- **Linux install coverage**: cross-distro install smoke on Debian, Fedora, and Arch, plus a GTK fallback path and an xvfb desktop smoke.
- **Resilient API-runner parsing**: the API runner parses each finding independently against the raw OpenAI client, so one malformed finding drops itself and the call still succeeds, with dropped findings counted and logged. Connection errors get a generic message rather than a misleading timeout hint, and OpenAI SDK retry compounding is capped.
- **Cross-platform cancel escalation**: cancelling an external run escalates from SIGTERM to SIGKILL across the process group, so runs no longer orphan, and the evaluations list dedupes by project and run id rather than job id.
- **Unified coverage line on dimension cards**: the separate partial badge and stale label are replaced with a single muted coverage line.
- **Faster dismiss on large projects**: dismiss responses carry a slim scores payload (hundreds of bytes instead of hundreds of KB) and the accumulated dashboard rollup is marked stale rather than refetched immediately, cutting click-to-rescore from seconds to under a second on large projects.
- **Overview stays visible during evaluations** instead of being replaced while a run is in progress.
- **Narrow-viewport layout**: the overview score-history and dimensions panels stack on narrow viewports instead of overflowing.
- **API prompt prefix ordering**: the constant prefix leads and the variable file block trails, improving cache locality on the API path.
- **Faster manifest scanning**: it prunes skip directories and memoizes file hashes, and dimension estimates reuse a single classification pass.
- **Sharper CI PR reviews**: the run fails loudly when the model is unreachable instead of passing green while every call 404s, and reviews post inline comments only on the changed lines, listing any findings outside those lines in the summary so nothing is silently dropped.

### Fixes
- **Legacy dismissed findings survive the upgrade to 1.2.0**: `dismissed.json` is now folded into `actions.jsonl` keyed off a sentinel marker, even after `actions.jsonl` already exists. Previously, upgrading projects lost their Dismissed tab and saw hidden findings reappear in scores.
- **'major' severity no longer silently dropped**: the schema now accepts `major`, which a CHECK constraint had been rejecting on every major finding.
- **Findings nested in finding-shaped wrappers are counted**, not swallowed, and truncated parses are treated as lossy so they are not cached as complete.
- **Scoring handles findings with no requirement id** when dismissing and restoring, rather than skipping them.
- **Dashboard serves CLI scores from the evaluation JSON**, removing an overlay that could diverge from the canonical scores, and the projector and rescore paths share the CLI engine's confidence-level rule.
- **Failure-streak breaker trips deterministically**: a final scan runs on stop so the circuit breaker no longer flakes on the last dimension.
- **Source tarball excludes `node_modules`**, with a CI guard so it cannot creep back in.
- **QuodeqBar packaging** points the PyInstaller add-data at the correct icon path.
- **pywebview multi-monitor drag** no longer jumps the window off-screen.
- **Side-pane window registration** no longer loops on `setState` when re-registering the same spec.
- **Principle names restored on the violations page** after the internal `principle` to `practice_id` rename.

### Migration safety
- **Schema upgrades self-heal instead of bricking a run**: every per-run `evaluation.db` migration step recovers if an upgrade from 1.1.2 is interrupted (not only the v3 to v4 step), a both-present migration keeps the original rows, and a database written by a newer binary or otherwise unreadable falls back to the JSON eval files instead of crashing the scores or the dashboard.

## [1.1.2] - 2026-05-10

### Fixes
- **Adequate vs Poor/Critical color in light theme**: the legend's Adequate band was indistinguishable from Poor/Critical in the daruma light theme. Tokens now give it its own hue.
- **App icon ships in the wheel**: pipx and pip installs now find the bundled icon, so the desktop app launches with the correct icon instead of a default one.

### Docs
- **README example block**: the "What it finds" sample now uses Quodeq's actual severity labels (CRITICAL/MAJOR/MINOR/COMPLIANT) and the COMPLIANT row cites the CWE the code defends against.
- **Help → Violations & Fix Plans**: added a worked example block under Severity levels that mirrors the README, and renamed COMPLIANCE to COMPLIANT to match the badge shown on finding cards.

## [1.1.1] - 2026-05-10

### Features
- **Content-addressed result cache (V2)**: replaces the legacy fingerprint-based cache. Findings are keyed by file content + dispatch parameters, persist incrementally across runs, and survive interrupted scans. Per-dimension `cache_stats` markers report hit/miss telemetry. The old `QUODEQ_CACHE_V2` flag is gone, V2 is the only path.
- **Per-file completion markers**: subagents now call `mark_file_done` to signal a file finished cleanly. Only files with an `ok` marker are persisted to cache, so a crashed or killed subagent can no longer poison future runs with partial results.
- **Consecutive-failure circuit breaker**: a streak of failing dimensions trips the breaker and exits with `exit_reason=failure_streak` instead of grinding through every remaining dimension.
- **Per-dimension state machine**: each dimension's lifecycle (pending, running, complete, incomplete) is tracked in `dimensions.json` and surfaced via the API status endpoint. Discard wipes V2 cache entries for incomplete dims so resuming reanalyzes them cleanly.
- **Live history view**: in-progress runs in History show a live dim summary as dimensions complete, refresh on tab open (not just poll tick), and flip to terminal state immediately when a run is cancelled. SSE-driven; the recurring poll is gated off when SSE is enabled.
- **Severity filter on detail reports**: file and principle detail reports plus their fix plans now honor the active severity filter.
- **Clickable violation drill-downs**: violation counts on the overview, run, dimension, and table views drill into the matching findings.
- **Dismiss findings from file detail**: previously only available on the violations table.
- **3-button cancel modal**: replaces the checkbox-style modal with a clearer 3-button layout.

### Improvements
- **Periodic per-file cache persist** during dispatch so a hard crash doesn't lose all in-flight work.
- **Cache pre-writes carry-forward findings before dispatch** so a single dedup pass is enough.
- **Side-pane window registration**: re-registering a window with the same spec ref is a no-op; differing specs replace the docked window cleanly.
- **Tighter cancel button and partial-run chip tooltip** on the running-eval header.

### Fixes
- **BrokenPipeError on success-log no longer marks a successful dim as incomplete**.
- **Cancel waits for `status.json` to reach a terminal state** before returning, so the UI never races ahead of the worker.
- **History row shows the correct dim count** for multi-dim runs (3-dim runs no longer rendered as single-dim).
- **History row shows a "performing an evaluation..." placeholder** for running rows instead of empty space.
- **Project queries invalidate on eval start** so History reflects the new run immediately.
- **Dashboard self-heals stale dim cache** by validating against the on-disk eval file count, and bypasses the dim cache entirely for in-progress runs so finished dims surface mid-run.
- **`--clean-scan` invalidates V2 cache entries up front** instead of only bypassing reads.
- **Windows cp1252**: replaced unicode arrows and em-dashes in analysis output that crashed on Windows consoles.
- **`dimensions.json` written to `run_dir`**, not `work_dir`.
- **API runner emits `file_done` markers** via the FindingsRouter, so API-driven runs get the same crash-safety as CLI runs.
- **Pre-marker cache entries invalidated** via a schema-version bump.

## [1.1.0] - 2026-05-08

### Features
- **llama.cpp as a first-class local provider**: select llama.cpp in the provider tabs alongside Ollama. Auto-detects the server log file at platform-standard paths (`~/.quodeq/logs/llama-server.log` on macOS/Linux), with an opt-in console viewer via `LLAMACPP_LOG_FILE`.
- **Import project from exported zip**: bring a project archive in via the new import flow on the Projects page.
- **Online-repo flow rebuilt around clone-on-add**: URL inputs in the wizard now route through a Clone Target step instead of a separate "clone-to-local" step on Re-evaluate. Choose a persistent location or use ephemeral clones that get cleaned up when the run finishes. Last-updated freshness shown on the project page; legacy online projects badged as setup-incomplete with a Complete Setup CTA. Re-evaluation blocked on ephemeral-completed projects.
- **Project name in headers**: shown in the overview header and on the running evaluation panel.
- **Live history polling**: history view auto-refreshes while a run is in progress; overview shows an empty state until the first run completes.

### Improvements
- **Cheaper, more reliable eval-log streaming**: SSE bursts are coalesced into one render per frame via `requestAnimationFrame` (with a 50ms timer fallback for hidden tabs), and the side-pane spec is decoupled from the log array so only the log body re-renders on each batch. Follow button now re-snaps to bottom on resize and scrollHeight changes.
- **Heartbeat log line trimmed**: progress line shows dimension/agents/files/scores with a remaining-count in the files segment and a pipe separator between violations and compliance.
- **History trend**: running runs show "running" with their scored dimensions instead of "in progress".
- **UI polish**: subtler import-project pill, sidebar count badge with breathing room and responsive scaling on narrow widths, more compact Evaluate panel with provider badge aligned to the topbar style, bolder filled term-btn weight, dimmer side-pane icon buttons at rest, log panes simplified (copy/download removed).
- **Filenames in finding cards never truncated**; pill click no longer toggles the row, and ellipsis only kicks in on real overflow.
- **Scroll resets on screen change**.
- **Dependency bumps** (Python and npm).

### Fixes
- **Job watchdog**: respects the user's `deadline_at` instead of a hardcoded 2-hour limit.
- **Windows file-lock contention**: retries when another process is briefly holding the lock; cleans up on persistent failure.
- **Incremental analysis**: incomplete prior runs no longer carry forward, affected files are re-analyzed.
- **Confidence threshold scales with project size**: small projects no longer have findings filtered too aggressively by a one-size-fits-all threshold.
- **Run date_iso emits explicit UTC marker** so report timestamps roundtrip cleanly.
- **Overview**: excludes in-progress runs from the accumulated view.
- **URL detection**: case-insensitive regex; localStorage and error-message paths covered.

## [1.0.10] - 2026-05-06

### Fixes
- **Ollama / API providers**: subagents no longer wipe the shared findings file mid-scan when a batch yields no usable source files (e.g., all skipped because they exceed the 15 KB API limit). Findings from other agents in the pool were being silently lost, surfacing as a scan-progress reset to "0 findings".
- **Windows EXE build**: the release script no longer fails on GitHub Actions runners. PowerShell was interpolating `$RepoRoot` (e.g., `D:\a\quodeq\quodeq`) into a Python string literal where `\a` got decoded as a bell character, breaking path resolution. Version is now parsed with PowerShell's native regex.

## [1.0.9] - 2026-05-06

### Features
- **Onboarding overhaul**: terminal-styled wizard, empty-state pages for Overview, Map, Violations and History, project-data tabs hidden until the first run finishes, silent resume when adding an existing project, standards picker honors the visible-standards setting.
- **Confidence scoring for findings**: each finding now carries a confidence value. Three new context layers downweight likely false positives. Path-role classifier deprioritizes non-prod files. Project-shape detector deprioritizes hosted-service findings on services you don't host. A project-local precedent corpus deprioritizes findings already dismissed in past runs.
- **Permanent finding deletion**: Delete and Delete all in the Dismissed sub-tab, with principle and file suppression.
- **Total time limit with live countdown**: per-run hard cap shown in the dashboard and the CLI.
- **Incremental by default**: analysis carries forward findings for unchanged files. Pass `--clean-scan` (CLI) or `cleanScan: true` (API) to force a full reanalysis.
- **`cleanScan` API field**: new boolean field on the `POST /api/evaluations` payload (default `false`). Replaces the deprecated `incremental` field.
- **Persistent shallow-clone cache**: online repos are reused across runs instead of re-cloned every time.
- **Job-running guards**: blocks double-evaluation and add-project flows while another job is running.
- **Settings tabs rework**: provider tabs gain inline help hints and friendlier copy.
- **OpenRouter Test button**: now actually works end-to-end, plus settings input polish.

### Improvements
- **Cross-platform window chrome**: native chrome on Windows, unified macOS traffic-light dots across screens.
- **Sidebar polish**: cleaner collapse animation (labels fade rather than slide), circular highlight on collapsed icons, ellipsis for long repo names, hidden labels and badges when collapsed, reordered nav.
- **Re-evaluate UX**: toggles moved top-right, terminal restyle, snackbar feedback for blocked actions, Hide removed, label clarified to Re-evaluate.
- **Header and detail-page polish**: header tooltips, principle descriptions, standards descriptions, explorer header, dimension and principle and file detail pages share a unified header.
- **Help, Evaluate, score-history**: refreshed copy, layout polish, score-history click target fixed.
- **Wizard polish**: scroll behavior, X-icon close, panel-style burger, scoped StatStrip and radio theme.
- **Project card polish, dark grade contrast, sidebar reorder.**

### Fixes
- **Phantom running evaluations**: cancel now stale-promotes when SIGTERM has no target, plus a UI escape hatch for stuck rows.
- **External runs**: `deadline_at` surfaces on snapshot, CLI-started runs auto-resume on the Evaluate tab, eval-log SSE stays alive through the preparing phase.
- **Overview**: falls back to the latest complete run when an in-progress run has scored zero dimensions.
- **Default time limit**: propagated into the analysis subprocess.
- **Snackbar feedback**: no-standards snackbar now also fires from the re-eval card.
- **Project navigation**: waits for projects to load before bouncing off project-data tabs, empty-state Case A correctly routes to the Projects tab.
- **Dismissed list**: no longer silently capped at 500 entries.
- **Desktop close dialog**: ignores stale running jobs with no live project.
- **API hardening**: input validation, path and signal safety, capped unbounded reads and lists, hardened standard-id path, export filename, tooltip helper.
- **macOS launcher**: pinned version bumped to 1.0.9 fallback install.
- **Tests**: stale UI vitest mocks refreshed, legacy `--incremental` + `--diff-from` regression test made CI-safe.

### Deprecations
- **`--incremental` CLI flag**: deprecated, no-op alias for the now-default behavior. Will be removed in the next release. Use `--clean-scan` to force a full reanalysis.
- **`incremental` API field**: deprecated, inverted alias for `cleanScan`. Migrate to `cleanScan: false` (use cache, default) or `cleanScan: true` (force reanalysis).

## [1.0.8] - 2026-05-02

### Features
- **Side-pane workspace**: multi-window dock replaces the single Report pane. Open the markdown Report or any fix plan for a run/file/dimension in a draggable side pane, with a log viewer for evaluation, server and Ollama streams.
- **Live updates over SSE**: dashboard subscribes to `/api/evaluations/<jobId>/events` for status, dimension and finding events instead of polling. Snapshot + tail reconnect via finding id.
- **Indexed findings store**: per-run SQLite projection of the JSONL (`evaluation.db`) for instant filters and detail-page lookups across multi-thousand finding runs. JSONL stays the durable truth; `QUODEQ_DISABLE_SQLITE` kill switch.
- **Live scan progress**: collapsible per-dimension breakdown, per-dim time estimates, pool autoscale, and partial-work salvage when a run is cancelled or a subagent crashes.
- **Resource observability**: per-run sampler logs RSS, FDs, threads and Ollama process state every 60 s for diagnosing long scans.
- **Explorer redesign**: dimension overview rebuilt around terminal-polish cards; file, principle and dimension detail pages now share a unified header.
- **Clean scan toggle**: incremental and clean modes collapse into a single switch, with carry-forward gated on the flag.
- **In-dashboard Markdown report viewer**: renders the run report with react-markdown and remark-gfm; download saves the file via the native dialog.

### Improvements
- **TanStack Query migration**: dashboard reads/writes go through TanStack Query. Instant run-switch via shared cache, placeholderData and prefetch.
- **Bundle splitting**: markdown vendor chunk and lazy route pages cut initial JS for the dashboard.
- **Side-pane performance**: deferred body mount, memoized renders, `contain` + `content-visibility` during resize, and smooth splitter drag via direct DOM writes.
- **Run-index batching**: upserts are batched and standards grouping is memoized.
- **Prompt tuning**: 4 evaluation prompts shortened by ~42% with no behavior change. Minor-severity bar tightened to drop hedged or speculative findings.
- **Centralized scoring view**: a single `scoring_view` package and shared trust predicate cover accumulated, dashboard and per-dim resolution.
- **Settings + console polish**: tidier provider rows and console actions.
- **CI nightly**: timeout raised to 720 minutes to fit a full reanalysis.

### Fixes
- **OpenAI FD leak that aborted long scans**: plugged, with surface cleanups bundled in.
- **BrokenPipeError handling**: scoring callback now retries to persist `evaluation/<dim>.json`. Loops no longer silently drop dimensions when the callback raises.
- **Incremental cache invalidation**: prompt fingerprint splits rules from non-rules edits so non-rules tweaks don't blow the cache. Prompt content is now part of the fingerprint.
- **Run salvage**: `files_read` and `source_file_count` populated from queue / `scan.json` when a scan is interrupted mid-flight.
- **History list**: in-progress rows clean up correctly, cancelled-but-partial runs render with a `partial` chip, clicking a still-running row with no scored dimensions is blocked, History tabs no longer show stale data via `placeholderData`.
- **Overview**: defaults per-dim cards and headline to the latest complete run, while still including in-progress runs where appropriate.
- **Window drag and topbar**: pywebview drag region on the topbar, controls reordered and standardized in height, compact drawer no longer leaks the icon rail or repo block. Sidebar version reads from server health instead of a hardcoded constant.
- **Confirm dialog**: hardened against XSS via DOM-based construction with a `variant` prop.
- **Detection corpus rebuilt**: project classification produces correct labels.
- **Analysis polish**: finding highlight widens to the full violation span, api-runner schema tightened to ground model findings, clean scan ignores prior findings instead of re-verifying them.
- **Resource utilization**: env-file injection capped, LRU cache and MCP child caps enforced, console virtualization tightened.
- **At-cap toast**: triggers from the toolbar Report and Fix-plan paths. Em-dash dropped from the message.

## [1.0.7] — 2026-04-25

### Features
- **History management** — filter cancelled/failed runs from the history list, per-run delete button with confirmation dialog, score_history chart no longer shows phantom partial-score points from interrupted runs
- **Run lifecycle resilience** — scans survive dashboard restarts (detached from API lifecycle), reconnected dashboards stream live violations and logs, cancel-and-close dialog fires when a scan is running on window close
- **macOS app identity** — dashboard shows the Quodeq icon in the dock + menu bar (not generic Python/document), About panel includes version, copyright and website/repo links

### Improvements
- **Evaluation prompt quality** — evidence gate (no absence-inference violations), tighter critical severity rubric (must describe concrete attack/failure), severity self-check for every finding, `minor` severity ceiling for test files, `max_retries=1` on structured output so a single broken JSON response doesn't silently cost ~6 minutes
- **Dashboard UX** — long finding/history lists lazy-render via CSS `content-visibility: auto` (no JS virtualizer, no "Show more" pagination, LazyColumn-feel on modern WebKit/Chromium)
- **Setup** — README quickstart covers OS prereqs (Homebrew / apt / dnf / pacman) + provider choice (Ollama or agentic CLIs); prereq check on dashboard start aggregates missing Node + npm into one error with the correct multi-package install command; auto-fallback to `--browser` on Linux when `gir1.2-webkit2-4.1` is missing
- **CI / release** — PR-review workflow allows 0-findings runs when the incremental filter is active, uses COMMENT verdicts instead of APPROVE (GitHub Actions can't submit approvals via `GITHUB_TOKEN`); per-project CI config moved from `.quodeq/workflow.env` to `quodeq.env` at repo root; duplicate local Homebrew formula dropped in favour of the tap repo as source of truth

### Fixes
- **Dashboard exited silently on Linux** — now probes for GTK/WebKit bindings, falls back to browser mode with actionable install hints; webview stderr lands in `~/.quodeq/run/webview.log` instead of /dev/null
- **BrokenPipeError at scan end marked runs as failed** — transition now walks through finalizing → done; evidence data was always safe, status now reflects that
- **Close dialog never fired for any user** — long-standing bug from bad URL parsing plus Promise-unaware `evaluate_js`; polls a JS global every 100 ms until the user picks keep/cancel/back
- **Live violations panel empty on reconnect** — seed `partialDimensions` from the requested-dimension list when `current_dimension` is null; `dimensions` is now populated in external-job snapshots
- **External runs had no logs in the UI** — tail `run.log` from the run directory when serializing `ext-*` snapshots
- **Detail pages showed a huge empty scroll** — replaced the home-grown JS virtualizer with native CSS content-visibility, scrolls inside the app's single scroll container
- **test_shutdown_ignores_dead_process** used the wrong patch target, letting the real `_kill_tree` run on PID 999 and SIGTERM the test runner's process group on Linux CI

## [1.0.6] — 2026-04-15

### Fixes
- **Stale UI after upgrade** — dashboard now detects version changes and rebuilds the UI cache automatically via npm
- **Leaner package** — excluded pre-built static files and node_modules from the wheel (27MB → 847KB); UI builds from source on first launch
- **npm install on rebuild** — always runs npm install before build to catch new dependencies after upgrades
- **Onboarding dots** — hide Settings, Evaluate, and console dot indicators when evaluations already exist

## [1.0.5] — 2026-04-14

### Features
- **Galaxy view** — unified galaxy visualization with file system and standards constellations, folder drill-down, circle pack info panel, and legend
- **Fix plan risk analysis** — risk analysis section added to fix plan templates
- **Onboarding dots** — one-time sidebar dot indicators for setup flow (settings, evaluate)
- **Console pop-out** — open evaluation console in system browser from native window
- **Dashboard as default** — running `quodeq` without a subcommand opens the dashboard

### Improvements
- **Unified scoring** — server-side rescore pipeline, accumulated rescore per specific run, history rows match overview scores
- **Code quality** — resolved 640+ violations across maintainability (426), usability (65), flexibility (82), performance (46), and security (22)
- **Map visualization** — circle pack smoothness, shared map navigation, dark mode toggle, galaxy particle sizing
- **Native window** — larger window control dots with hover glow, native Save dialogs for standard/project downloads
- **Code-split recharts** — eliminated 500kB chunk warning via lazy loading
- **CI** — drop `--extra api` (instructor now a base dep), test on Python 3.13 only

### Fixes
- History chart bar colors update on theme change
- Map dark mode uses current theme family instead of hardcoded value
- Evaluation form respects current standards visibility
- Skip scoreless dimensions so cards show last valid evaluation
- Emit Report path marker so dashboard auto-refreshes after evaluation
- File locking for dismissed findings storage to prevent corruption
- Bundle schemas, configs, and full module tree in PyInstaller spec
- Evaluation subprocess works in frozen .app bundle
- Include package version in UI build hash so upgrades trigger rebuild

## [1.0.0] — 2026-04-10

### Features
- **Desktop app** — standalone Quodeq.app (macOS) and Windows .exe packaging with CI build workflow
- **Help tab** — comprehensive usage documentation covering getting started, providers, evaluations, violations, code map, standards, and AI-generated custom standards
- **Scoped evaluations** — narrow analysis to a subdirectory or branch within a repository
- **Inline verification** — replaces separate verification phase for faster incremental scans

### Improvements
- Instant "Closing..." overlay on window close with faster shutdown (4s to <1s)
- Kill running evaluations on shutdown with close confirmation dialog
- Cache dashboard data per run for zero-flash date switching
- Sidebar-only scroll and loading state improvements

### Security
- Path traversal fixes using is_relative_to and validate_path_segment
- SSRF protection on cloud provider URLs (private network blocking)
- XSS escaping in webview close dialog and log route
- API key sanitization in error responses
- System directory scan blocking (/proc, /sys, /dev, /etc)

### Reliability
- Thread-safe rate limiter with Lock
- Crash guards on env var parsing (int() with fallback)
- None payload guards on standards CRUD routes
- Temp file and worktree leak fixes
- Narrowed bare except Exception to specific types

### Code Quality
- Performance: single-pass iterations, pre-indexed Maps, useMemo, chunked file hashing, bounded fetch concurrency
- Maintainability: replaced bare except/pass with logging, fixed stale __all__, moved inline imports to module level, extracted duplicated code
- Test coverage increased from 74% to 86% (+1011 tests)

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

[1.0.5]: https://github.com/quodeq/quodeq/compare/v1.0.0...v1.0.5
[1.0.0]: https://github.com/quodeq/quodeq/compare/v0.9.0...v1.0.0
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
