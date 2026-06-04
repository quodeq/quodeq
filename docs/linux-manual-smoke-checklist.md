# Linux manual desktop smoke (run per release)

CI covers the unit + integration suites, cross-distro install, the GTK-missing
browser fallback, and an `xvfb` headless launch. What a human still confirms is
the real native window on an actual desktop session, under BOTH display servers.

> Note: `docs/` is gitignored in this repo (only `docs/adr/` is tracked). This
> file is force-added so the checklist is shared.

Per release, on a Linux machine with `python3-gi` + `gir1.2-webkit2-4.1`
installed (`sudo apt install python3-gi gir1.2-webkit2-4.1`, or the
Fedora/Arch equivalents):

- [ ] **X11 session:** `quodeq` opens the native GTK window; the dashboard UI renders; an evaluation runs and findings stream in; closing the window leaves no orphaned `quodeq`/python processes.
- [ ] **Wayland session:** same as above.
- [ ] **Without the GTK bindings installed:** `quodeq` prints the install hint and falls back to opening the dashboard in the browser (no crash).
- [ ] **`quodeq --browser`:** opens the dashboard in the default browser regardless of GTK.

Record the distro, the display server (X11/Wayland), and pass/fail per item on the release.
