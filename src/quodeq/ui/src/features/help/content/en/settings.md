## Settings

**Settings** is one sheet of five groups: *Evaluation*, *Assistant*, *Connections*, *App* and *About*. Each group's name sits in a gutter on the left with a line saying what it holds and its current state, for example the provider and model in use, whether you are signed in to GitHub, or the version you run. A dot beside that state marks whether all is well or something needs you. Most of it is set once and forgotten.

### Evaluation

Which AI reads your code, how long it may take, and how findings become grades.

- **AI Provider** picks who runs your evaluations: a CLI you have signed in to (Claude Code, Codex, Gemini, Antigravity, Copilot), a hosted API (OpenRouter or a custom OpenAI-compatible endpoint), or a local model server (Ollama, llama.cpp, oMLX). A provider that is not installed shows how to install it.
- **Model** is the model for that provider. Claude Code, Codex, Antigravity and GitHub Copilot list the models your account can use, and the one the CLI picks by default reads *(default)* (*Other model id* takes one that is not listed); Gemini CLI takes a typed id. A local server lists the models it has; llama.cpp shows the GGUF it has loaded. A local server's own row shows whether it is running, its address (click it to copy) and a console button for its log.
- **API key**, for hosted and some local providers, is write-only: paste a key and press **save key**. quodeq stores it outside the browser, in your system keychain by default, and the row only ever says *key saved*, with **replace** to enter a new one. The key itself is never shown again.
- **Test** checks the connection to a hosted model and reports its latency.
- **Evaluation time limit** stops a run after that long. Whatever finished in time is scored, and the next run continues from there.
- **Max parallel agents** is how many subagents work side by side, from 1 to 10; local servers can measure what your hardware can serve.
- **Effort**, right under the model for Claude Code, Codex and Antigravity, is how hard the model thinks about each file. It offers the levels the chosen model takes; **Default** leaves it to the CLI, and a change re-analyses every file on the next run.
- **Command**, on a CLI provider, is the command that launches the CLI, checked as you leave the field.

The *Results* section under the model:

- **Live findings** chooses what the live feed shows while a scan runs: **New only**, the findings this scan produces, or **All**. Findings reused from unchanged files stay in the final report either way.
- **Grade formula** opens the formula editor with **open editor ›**. Changes there rescore all runs. See the **Grade Formula** help section.

- **Storage** keeps the disk use of your evaluations in check. **Space used** reads, for example, *4.2 GB of evaluations on this machine · 31 of 120 runs archived*. **clean now** first shows a preview, how many runs it would archive and about how much space that frees, and then runs in the background, counting the runs as it goes. **Clean up after start** is the off switch for the automatic cleanup. While it is on (the default), quodeq tidies finished runs and archives the ones beyond the number you keep by itself after start-up, once the scores have loaded, and **Space used** counts the runs as it goes. While it is off, nothing happens on its own and **clean now** still works. Tidying removes scratch files a finished run no longer needs and compacts its database. It applies to every finished run, the newest one included.
- **Runs kept in full per project** sets how many of each project's newest finished runs stay as they are: 5, 10 (the default), 25, or all. Every other finished run, cancelled ones included, is archived at the next pass, whatever its age. Archiving compresses a run's event log and evidence in place, which makes those files about 76% smaller, compresses its reports, about 80% smaller, and drops the run's database, which is rebuilt from the event log in a couple of seconds when the run is opened. The reports stay readable in place, and grades and history do not change. A run too big to restore safely is left unpacked. Cleanup never touches a project with an evaluation in progress, and it never archives the newest run of each dimension. With **all** it archives nothing new. Runs already archived stay archived and still open as usual. The *archive runs untouched for* choice of earlier versions is no longer used.
- **Keep the findings of archived runs for** sets how long an archived run keeps its archive: 3 months, 6 months, 1 year, or forever (the default). After that time the archive is removed for good and the run becomes *report only*: it keeps its grades, its dismissals and its reports, it still shows in History, the trend, the map and run comparisons, and its report opens at once. It cannot be rescored under a new grade formula, a dismissal made later does not reach its grade, and the assistant cannot search its findings. Choosing a period asks for a confirmation first, since this cannot be undone; the next clean up then removes the findings of every archived run older than that. With **forever** nothing is removed.
- **Reading an archived run.** The project list, trends, the History list with the files and time of the run you select, and a dimension page's comparison with the previous period all read an archived run without restoring it. Two things restore one: opening the run itself (its run page, its findings or its report, for example with Enter on a History row), which takes a few seconds and keeps it unpacked for 30 days; and applying a grade formula, which rescores every run and so restores every archived run, each staying unpacked for 30 days. Cleanup waits while such a rescore runs. A finding you dismiss later shows in an archived run's grade once that run is opened.
- **The first start with archiving.** The first time quodeq starts with this rule and finds runs beyond the number you keep, or archived runs whose reports are not compressed yet, it only tidies. The Storage section then says how many runs the next start will archive, how many archived runs get their reports compressed, about how much space that frees and, when a period is chosen under **Keep the findings of archived runs for**, how many runs lose their findings for good, so you can choose a larger number, pick **forever**, or turn **Clean up after start** off before anything is archived or removed. Set `QUODEQ_STORAGE_CLEANUP=0` to turn the automatic cleanup off from the environment.
- **delete all evaluation data**, in the **⋯** menu of the Storage row, removes every project's runs, findings and history from this machine. You confirm by typing `delete all`. Your repositories and settings are not touched, and it refuses while an evaluation, a clean or a grade formula rescore is running.

### Assistant

Which model answers in the assistant. **Default** follows your evaluation provider and model, **Custom** lets you choose another provider and model for the assistant alone. The assistant itself is switched on or off under *App*, in **Toolbar**.

### Connections

Your GitHub account, the evaluations repository, and the local server.

- **GitHub access** shows how quodeq reaches GitHub: signed in through quodeq, using your `gh` login, or not signed in (your own git setup). **sign in with GitHub** starts the sign-in, and **sign out** forgets only the token quodeq stored. See the **Git access** help section.
- **Shared repository** holds the address of the git repository you publish evaluations to, yours across machines or shared with anyone who has access, with **change** and **disconnect**, and **Share code snippets**, which is off by default. The **Shared Repository** help section walks through connect, publish, pull and disconnect.
- **Local server** shows the **Quodeq server** row: *Running*, *Not reachable* or *Checking…* while it asks. While it runs, the row shows its address (click it to copy), a caption with its version and PID, and a console button that opens the server log. When it is down, the row says how to start it again and that it is checked again every few seconds. The address is for reference: typed into a browser it only shows how to start quodeq, because the server answers the window or browser tab quodeq opened and nothing else. `quodeq dashboard --browser` opens the dashboard in a browser.

### App

How quodeq looks and which tools sit in the toolbar.

- **Appearance** sets the mode (system, light or dark) and the theme, a color palette. Themes change accent colors and surface tones; the layout stays the same.
- **Toolbar** turns the assistant (**Enable assistant**) and the terminal (**Enable terminal**) on or off. Both are on by default. **Restart terminal** closes every terminal session and opens a fresh one, after asking. See the **Assistant** and **Terminal** help sections.
- **Desktop app**, in the desktop app on macOS, has **Show menu bar icon**, which keeps quodeq in the menu bar to monitor, start and stop the dashboard even when the window is closed.

### About

The last group holds the version, updates, the welcome and links: the *Updates* section, *Getting started*, then links to the website, the repository, the blog and the changelog.

- **Getting started** has **show welcome**: it opens the welcome and the first-run steps again, even if you skipped them before. Nothing else changes; your projects and settings stay as they are. If you already have projects or a connected repository, the welcome adapts to say so, and showing it never marks onboarding as skipped.

### Updates

quodeq checks PyPI and GitHub once a day for a newer version. When one exists, a banner appears at the top of the dashboard and the *Updates* section shows the version jump plus the way to get it: the exact upgrade command for your install (pipx, uv, or Homebrew) or a download. When Quodeq knows how it was installed, an *Install* button runs that command for you, then *Restart now* loads the new version when you are ready. Install waits while evaluations run, because the upgrade replaces code they still use. Dismissing the banner silences that version; the next release brings it back.

- **check now** asks immediately, ignoring the daily throttle.
- **Automatic checks** turns the daily background check on or off.
- Set `QUODEQ_NO_UPDATE_NOTIFIER=1` to disable automatic checks and CLI notices entirely.

### After an update

The first start after an update can invalidate quodeq's score caches. The dashboard opens right away and rebuilds them in the background, newest projects first: project cards show a pulsing placeholder while their grade recomputes, and a *Refreshing scores* progress bar on the loading and Overview screens counts through the projects being prepared. Anything you open jumps the queue. If the very first request still times out, the screen offers **Retry**; retrying is safe and never duplicates work.

The same background rebuild runs whenever score caches need re-deriving for other reasons, for example after relocating a repository or clearing `~/.quodeq`.
