# Help screenshot capture checklist

These screenshots ship in the app bundle and rot when the UI changes.
Recapture whenever the pictured screen changes visibly. This checklist is
also the spec for a future automated capture script.

## Common settings

- Viewport: 1440x900, deviceScaleFactor 2 (retina).
- Theme family: daruma. Capture BOTH modes: `dark` and `light`
  (set `cc-theme-mode` in localStorage before load, alongside
  `cc-theme-family: daruma`).
- Subject data: a project with at least one completed run that has an
  event log. The quodeq self-scan project works well (in the sidebar
  and Projects list it shows as `quodeq`, the project whose path is the
  quodeq repo itself). Never a customer repo.
- The dashboard remembers the last-selected project across page loads,
  and that default project may not have a completed evaluation (its
  overview will show an empty state). Do not assume the default
  selection is usable: always explicitly pick the target project from
  the Projects list before navigating to the screen being captured.
- Format: WebP, target under 150KB per file. Conversion (`cwebp` from
  the `webp` Homebrew formula; this machine's ffmpeg build has no
  libwebp encoder, so `ffmpeg -c:v libwebp` is not usable here):
  `cwebp -quiet -q 82 shot.png -o out.webp`
  Verify integrity by decoding back: `dwebp -quiet out.webp -o check.png`
  and inspecting `check.png`.
- Naming: `<topic>.<mode>.webp` (e.g. `grade-formula.dark.webp`).
- Wire new pairs through `<HelpFigure srcDark={...} srcLight={...} />`.

## Navigating with Playwright against the live dashboard

- The sidebar's projects entry has NO fixed title/label. Its `title`
  attribute is the current repo name (or literal `"project"` before one
  has loaded), so it cannot be selected with `button[title="projects"]`.
  There are three `<nav class="sidebar-nav sidebar-block">` blocks
  (overview group, evaluate, projects); the projects one is the last,
  right before the sidebar spacer/footer. Selector that works:
  `nav.sidebar-nav.sidebar-block:last-of-type button.sidebar-nav-item`
- After that click, project cards render with class `.project-card-name`.
  Match the target project by exact text and click it, then wait
  (~1.5s) for the app to navigate to that project's overview and load
  its data.
- Only then click `button[title="settings"]`, then the `open editor`
  button in the "Grade formula" section, to reach the editor.
- After the editor loads, wait for the preview strip to debounce and
  fetch (~2.5s) before taking the screenshot, otherwise it may still
  show the loading/empty state.

## grade-formula.{dark,light}.webp

- Route: Projects, select the quodeq self-scan project, then Settings,
  "Grade formula" section, "open editor".
- Must show: the SEVERITY tab active with its three weight sliders
  (critical, major, minor), the preview strip populated with real
  per-dimension gauges (OVERALL plus one per dimension, each with a
  score and grade label), APPLY and RESET Q² buttons visible.
- Full page including sidebar (it is an orientation shot).
