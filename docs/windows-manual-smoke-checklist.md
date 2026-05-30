# Windows manual smoke checklist (run per release)

CI covers what it can headlessly: the unit suite is a blocking gate on
`windows-latest`, a nightly lane runs the integration tests on Windows, and the
packaged `.exe` is boot-tested (it must serve `GET /api/health`). What CI
*cannot* verify without a real desktop session is the actual native window
(pywebview + the WebView2 runtime) and the end-to-end UI. Run this checklist on
a real Windows machine for each release and record the results in the release PR.

> Note: `docs/` is gitignored in this repo (only `docs/adr/` is tracked). This
> file is force-added so the checklist is shared. See `docs/ui-map.md` for the
> full set of critical UI paths this checklist samples.

**Environment:** clean Windows 10/11 with the WebView2 runtime installed, using
the `Quodeq-<version>-Windows.zip` release artifact.

- [ ] Unzip and launch `Quodeq.exe`; the desktop window opens (no stray error or console window).
- [ ] Onboarding renders and completes (provider / model selection).
- [ ] Start an evaluation on a small repo; live progress and findings stream into the UI.
- [ ] Open a finding; the detail view renders; back/forward navigation works.
- [ ] The settings screen opens; a changed setting persists across an app restart.
- [ ] The logs side-pane opens and shows server / eval logs.
- [ ] Close the window; no orphaned `Quodeq.exe` or `python` processes remain (check Task Manager).

For each item record: pass/fail, the app version, the Windows build number, and
a screenshot of any failure. Attach the completed checklist to the release.
