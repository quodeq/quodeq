# Changelog

## [1.15.2] - 2026-10-28

### Fixes
- **Security, trusted certificates**: certifi 2026.10.19 drops the emSign root certificates whose intermediate CA keys were compromised ([GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)). Quodeq's HTTPS calls, model providers included, trust this certificate list. The macOS and Windows apps carry their own copy, so update them as well; a pip install that is not upgraded keeps the old certificates until `pip install -U certifi`.

### Improvements
- **Smaller install**: the package no longer carries the dashboard's source code, only the built dashboard and the help pages the assistant reads. The wheel goes from 5.2 MB to 3.3 MB.
- **Dependencies**: openai 3.35.1, pywinpty 3.1.0 (the Windows terminal), React 19.3.1, TanStack Query 5.104.5 and TanStack Virtual 3.14.21.

## [1.15.1] - 2026-10-20

### Improvements
- **Evaluate a pulled project**: a project pulled from another machine keeps the publisher's folder path, so the Evaluate card now asks you to locate its code (choose a folder, or clone it from its origin) and keeps Scan disabled until it is found. When the pull collides with a repository you already have, **evaluate yours** opens it on Evaluate, with pull as a copy as the fallback.
- **Help**: new Connect to CI and Desktop Apps (beta) pages; a custom standard is explained as its own dimension. The README is now a short landing page linking into the docs.

### Fixes
- **Evaluations failing at 0s**: an API server launched from a terminal that was later closed made every evaluation fail instantly with `init_sys_streams: Bad file descriptor`. The API and its jobs no longer inherit the terminal's stdin. Restart a running server to pick this up.
- **Scope paths**: `--scope ./src`, `--scope .` and `--scope ./` no longer abort with "No source files found under scope".
- **Map time-lapse**: the last step into today no longer reshuffles every circle; the time-lapse moves by what changed and ends on the same map as the Circle Pack.

## [1.15.0] - 2026-10-18

### Before you upgrade
- **One overall score**: a dimension that stopped on a failure streak keeps a provisional score, and every overall average now leaves it out: the Overview headline, the trend, the project card and Compare agree (only Compare did before). A run with such a dimension can show a different score in History after the update; the first start rebuilds the score cache.
- **One full score rebuild on first launch**: every run's cache version now carries its grade stamp (the fix for grades that stayed stale after a formula change), so the first start after the update rebuilds the scores of every project once, with the strip under the top bar showing how far along it is. The last known grades stay on screen, dimmed, until each project's new ones land.
- **Storage keeps a number of runs, not an age**: cleanup now keeps the newest 10 finished runs of each project in full (5, 10, 25 or all in Settings › Storage) and archives the rest, cancelled runs included, whatever their age: a project evaluated daily sees runs from last week archived. The first start after the update only tidies and shows a notice in Settings › Storage with how many runs the next start will archive and how much space that frees, so you can pick a larger number or turn **Clean up after start** off first. A 1.14 **never** carries over as **all**; the 1.14 age choice is no longer used.
- **Archives are smaller and reports are compressed too**: an archive no longer stores the run's database, which is rebuilt from the event log in a couple of seconds when the run is opened, and an archived run's reports are compressed in place; the pass after the notice compresses the reports of runs already archived. A run you open stays unpacked for 30 days. New files beside an archived run: `evaluation/<dimension>.json.gz`, `scalars.json`, `precedents.json`, and `grades.stamp` beside every database.
- **Going back to 1.14 after this update**: 1.14 cannot read a compressed report, so an archived run shows no dimensions there until this version opens it first (opening it in 1.14 first restores the archive without the reports). A run whose findings were removed (see Storage below) shows no results at all in 1.14.

### Features
- **Storage, an opt-in cold tier**: a new choice in Settings › Storage, **Keep the findings of archived runs for** (3 months, 6 months, 1 year or forever, the default), removes the findings of runs archived longer ago than that; such runs stay in History as **report only** with their grades, dismissals and reports, open at once, still count in the trend and still compare, and cannot be rescored or searched. Choosing a period asks for a confirmation first, since it cannot be undone; the clean now preview and the first-start notice say how many runs it concerns.
- **Evaluate on a remote project**: a remote project keeps its **Evaluate** action and shows a card that pulls a local copy first (pull, review, score), with a toast that brings you back if you moved away.
- **Principle page grouped by requirement**: the findings of a principle open grouped by requirement, the worst one first, with a requirement filter in the bar, search, and open all or fold all; the requirements rail is gone.
- **Finding rows and detail redesigned**: two-line rows (the title, then severity, path, principle and dimension), a detail that leads with the title, where it is, why, the rule and the code, one row of actions (fix plan, open file, dismiss), and **dismiss** as a menu that can dismiss this finding, every finding of the rule in the project, or in the principle. The principle and file pages show a finding the same way.
- **Dimensions header counts what is not evaluated yet**: the Quality dimensions header ends with how many standards are switched on but not evaluated and an **evaluate** action, with their names in the tooltip, replacing the line under the cards.
- **Code in reasons as chips**: backticked code in a finding's reason renders as amber chips.

### Improvements
- **Sidebar badge**: counts the open findings, the number the Violations page leads with, instead of criticals plus majors.
- **History**: the what-changed strip appears only once two runs compare against the same model, and the run card says *1 dimension*.
- **Assistant**: when no session can start, the drawer says why and offers **open settings** in place of the suggestions, with the input disabled.
- **Labels**: the score history reads *3 weeks* instead of *3w*, the since line says *rules opened*, and the Map head says *violations to compliance 1:3*.
- **Score history**: the history draws from the second evaluation on and shows a single week or month as one bar with its minimum, maximum and average; week buckets are labelled with their date range; the radial is left out under three points and takes the whole row while the history is hidden.
- **Grade formula page**: the chart keeps its frame while the projects load.
- **Headers**: a wrapped page header spans the full width.

### Fixes
- **Stale grades after a formula change**: a read that raced the rescore no longer pins the old grades in the Overview, Compare and History.
- **Code blocks**: a code block no longer scrolls inside itself and catches the page scroll.
- **Principle dismissals from a file page** find their run again (hydrated rows keep their dimension).

## [1.14.0] - 2026-10-17

### Before you upgrade
- **Every grade changes**: the default grade formula moves to v7. A critical finding now weighs 7.5 (was 4) and a minor one 0.15 (was 0.25), with a slightly gentler curve and a lower floor for principles with majors only. Runs already on disk are re-graded under the new formula, so nothing needs to be re-analysed. A custom formula saved under 1.13 is set aside: the Grade formula page says "Q² defaults active, older custom formula set aside", and the old file is copied to `grade_formula.v6.json` before you save or reset over it, so your tuning is kept.
- **One full rebuild on first launch**: the first start after the update rebuilds the scores of every project once, and the strip under the top bar shows how far along it is. The last known grade stays on screen, dimmed, until each project's new one lands.
- **Standards settings move onto this machine**: which standards are on for a project, and its requirement overrides, now live in `~/.quodeq/projects/<project-id>/standards.json` instead of `.quodeq/` inside the evaluated repository. The repository's `standards-visibility.json` and `standards-overrides.json` are copied once on first read and never modified or deleted, and quodeq no longer writes into a repository it evaluates. Shared and remote projects can now save these settings too.
- **Old runs get archived, after a notice**: from now on quodeq tidies finished runs after start-up and compresses runs untouched for six months in place, which makes their files about 76% smaller; the newest run of each dimension is never archived and an archived run is restored when you open it. The first start of 1.14 only tidies: Settings › Storage then says how many runs the next start will archive and how much space that frees, so you can pick a longer time or turn **Clean up after start** off first. `QUODEQ_STORAGE_CLEANUP=0` turns it off from the environment.
- **Going back to 1.13 after archiving**: 1.13 still opens your data, and Overview and Compare work, but it cannot read archived runs: they keep their grades and show no findings. To use them in 1.13, open each one in 1.14 first (or keep **Clean up after start** off until you are sure you are staying).

### Features
- **A grade formula editor that shows what a change does**: the editor is its own page, opened from Settings, and opens on what your grades would become. A **what changes** panel lists every local project with its old and new score and grade, the principles that move and the grade distribution today against the draft, live on every knob move. One chart places every principle by finding weight and score over the grade bands, with the draft and saved curves, and moved principles drawn with a stem back to where they are today; the chart stays pinned under the top bar while you scroll the knobs. The knobs are grouped by the question they answer (what a finding costs, where each grade starts, then fine-tune), each with its Q² default marked and the saved value struck through. Severity weights run from 0.05 to 25 on log-scaled sliders and always keep minor below major below critical. A review sheet lists the changed settings in words, the projects that change grade and the runs a rescore touches before Apply or Reset Q². The preview now uses the same accumulated score as the Overview, so a project no longer reads Poor in the editor and Good everywhere else. Slider limits come from the server, so the editor never offers a value the server refuses, and the grade bar shows initials on narrow segments and names its dividers by the grade that starts there.
- **The Map's Circle Pack shows where problems concentrate and where the code changes**: the pack is laid out in proportion to what each file holds and draws on canvas. **Concentration** colours each file and folder against the project's average weight per file, and files take their worst finding's critical, major or minor colour while better-than-average and clean ones read blue. **Activity** is now its own tab and lights the files changed often, from git when the project is a local repository. Light and dark paint with one rule set: glass folders, an inward glow on folders that are clearly worse or better than average, and none on wrapper folders such as `src/main/java`. Highlights are calmer, with three brightness levels and no veil pulsing on hover. A click goes to the circle under the pointer at any depth, a file click selects it and **view details** opens its findings. Collapsed folder chains are labelled by the first segment that names something. Clicking a dimension name in the Dimensions filter shows only that dimension.
- **Risk replaces the Risk Matrix**: a second Map tab draws the project's functional areas as a sky of bubbles, the riskiest nearest the centre. Distance follows the area's weighted findings per production file on the absolute **fix first** and **watch** lines, so a clean project's rings close in with nothing inside and a messy one's widen. Each bubble is one colour, its files show when you hover or select it, and the labels go to the densest fix-first and watch areas first. The hover card gives weighted issues per file, the kind, the issues by severity and the files. The Dimensions filter re-measures the sky over the chosen dimensions or one principle, and the dimension and principle pages open the Risk tab already filtered.
- **A time-lapse of the project's history on the Map**: switched on from the Map, it plays the Circle Pack and the Risk sky back by day, week or month (the same grouping as the Overview), from a dock along the bottom with an icon transport, a readout and a settings button for period and speed. Folders grow and shrink with what they held, colours blend between frames, Risk areas appear and fade as they did, and each frame counts issues exactly like the page header. A selected folder, file or area keeps its selection while the playback runs, and **view details** on a past day opens Violations as of that day, read-only, with a strip that names the day and **back to today**.
- **The Map works on remote projects**: a project from a shared evaluations repository now gets Risk, Activity and the time-lapse as well as the Circle Pack and Galaxy. Its Activity uses the publisher's git history, published alongside the runs, and falls back to an estimate from finding changes when the project was published without a working copy.
- **Violations is a findings workbench**: the count tables are replaced by the findings themselves, a list beside the selected finding's detail with its reason, code, references, fix plan and dismiss. The `$ grep -r` search runs across the full width over titles, paths, rule ids and principles, and a path-like query suggests folders and files that become a path chip. The severity, dimension, status and group menus sit in the page toolbar, folders browse worst first, and dismissed findings are a status rather than a tab, with restore and delete in the detail. Every place that used to open a file, folder, requirement, principle, area or dimension page now opens a scoped view of the same workbench, as a new step so Back returns, with list or cards, a draggable divider and read-only past runs. Bulk dismiss, restore and delete sit under a ⋯ menu.
- **The Overview, dimension and principle pages share one layout**: each opens with a header holding the score ring, a sub line with files, languages, model and when it was evaluated, and tiles for violations, pass rate, per 100 files and critical per 1k, each with its change since the previous day, week or month. A slim row above the header says what changed since the previous period (new, fixed, rule types opened and closed), or shows a tip when there is nothing to compare. Compact cards come next, weakest first, then the score history beside a radial, then **fix first** beside a **where** panel of areas, folders or files. Areas list every judged area worst first with a zone strip; a row opens the area's findings and a map icon opens it on the Map, folders open in the Circle Pack too, and the panel remembers its view for the session. Standards switched on but never evaluated are one line under the cards with **evaluate**. The dimension page's principle cards link to their radial spoke and fix-first rows, and the principle page has a requirements rail, a Risk tile and a score line over its last 16 periods. Pages load in their final shape, including the card count and heights the Overview last showed, so nothing jumps while a project loads or when you switch.
- **History is a run log**: a strip of new and resolved findings per run, then the runs grouped by day with their origin (nightly, PR, app or CLI), scope, new and resolved counts and score. The selected run opens as an Overview for that run, with its header, its dimensions as compact cards with what the run added and fixed, and fix first beside its folders or files. A cancelled run says so, how far it got and why, for example "Cancelled after 4h 34m (stopped by a signal). 4 of 6 dimensions finished". Archived runs carry an `archived` tag and are restored when you open them.
- **Share custom standards through the shared repository**: with a shared repository connected, the Standards page shows when it last synced with a **pull** button, and a sync column per standard (published, changed, update available, both changed, remote only). Each row offers the one action its state needs: **share**, **publish**, **update**, both with a confirm when both sides changed, or **install** for a standard that exists only in the shared repository. Publishing a project also publishes the custom standards its runs scored, and never overwrites a newer shared copy. Custom standards now carry created and updated dates and a version, the table shows each standard's source under its name, and the Type column shows only the kind (`iso`, `wcag`, `quodeq`, `custom`).
- **Storage settings**: Settings › Storage shows how much space evaluations take on this machine and how many runs are archived. **clean now** previews what it would archive and free before it runs, **Clean up after start** switches the automatic cleanup on or off, the archive age can be three months, six months, a year or never, and ⋯ › **delete all evaluation data** asks you to type `delete all`, removes only quodeq's project folders and refuses while an evaluation, a clean or a grade formula rescore runs. Cleanup waits for a rescore too, and never archives a run too big to restore. Lists, trends, History and the dimension page read archived runs without unpacking them. Repositories gains a size column, and deleting a project says how many runs and how much space go with it.
- **Archived runs travel through the shared repository**: publishing copies a run straight from its archive and leaves your local copy archived, commits only the run's own files, and a run that is old when first shared goes as a compressed archive without its database. On another machine it opens like a local archived run, and that machine builds its own database instead of trusting the publisher's.
- **The first run ends at the first evaluation**: after adding a project, **Who reviews it** lists the AI providers found on this machine without recommending one, with the CLI's own default model and effort preselected for Claude Code and Codex and your Settings choice kept. **start first evaluation** runs every dimension with no time limit. A git address only offers **save and close** while it downloads, and a folder that is already a project with runs offers **start evaluation**. A project's first evaluation starts with every dimension selected and no time limit, its scope reads *whole project*, and scan stays disabled until a model is chosen, saying so.
- **Never-evaluated projects say what to do next**: the Overview shows scan, review and score with a start button, keeping the "didn't finish cleanly" message for real failures. Repositories counts what is evaluated and offers **evaluate** on the row, the empty page shows the welcome's three ways in, and the app opens the Overview when a project's first run finishes.
- **Choose the model on Evaluate**: the model cell opens an in-place panel with provider, model and effort instead of sending you to Settings, and reads as the next step rather than an error. Evaluate now uses the app's page language, with a slim toolbar row, section panels and the full window width, and the running status, stop and view results sit in that row. While a run is live, each finished dimension shows its grade, score and a **results ›** link.
- **Settings sorted by what each setting controls**: the fourteen panels are now five groups, Evaluation, Assistant, Connections, App and About, each one panel with a gutter that names its current state. Cloud providers and oMLX get a write-only API key row stored outside the browser. The local server status is a settings row with a copyable address. Analysis models, Analysis power, Verify findings and GitHub's test access button are gone, and so is the Advanced fold.
- **Pick the model and effort from the CLI's own list**: for Claude Code and Codex the model field is a dropdown of the models your account offers, read straight from the CLI with no tokens spent, with the recommended one marked, a refresh button and **Other model id…** for anything unlisted. A new Effort setting under Model sends the CLI's effort flag, offers only the levels the selected model supports and keeps the CLI's default when left on Default. Results at one effort are never reused at another, so changing it re-analyses every file on the next run.
- **`quodeq upgrade`, and Install from the app**: `quodeq upgrade` runs the upgrade that matches how quodeq was installed (pipx, uv tool, Homebrew or this Python's pip), with `--dry-run` to print the command. For those installs the update banner now offers **Install**, then **Restart now**, instead of a command to copy; it waits while evaluations run, works only from this machine, and keeps the command and the tool's output when it fails. `quodeq restart` reopens quodeq with the flags and folder it was started with.
- **The terminal is yours again once the window is up**: a plain `quodeq` launch now returns the terminal when the window opens, and closing the terminal of a `--browser` or `--no-open` launch stops the API instead of leaving it holding the port. `quodeq status` shows the window, the API and running evaluations, exiting with 3 when nothing runs, and `quodeq stop` closes the window and the API while evaluations keep going. `--foreground` keeps the old behaviour, as do `--dev`, `--verbose` and Windows.
- **An assistant that sees the page you are on**: the assistant now knows the open page and its state (the selected area, the Where view, the open standard, the selected History run) and has tools for folders, history, run and project comparisons, dismissals, Risk areas, principle history, the grade formula and standards sync state. It reads the in-app Help before explaining anything on screen instead of guessing a definition. You can type while it works and messages queue until the turn ends, tool calls read as activity lines grouped per turn, and its read tools now work under Codex's sandbox. Asked for a standard, it interviews you first, proposes an outline sized to the source, refuses hollow drafts, links each requirement to its source page and shows the full outline on the card, which comes last; an applied standard is visible for the project from any screen.

### Improvements
- **Pages start on one line**: tool pages open with a slim toolbar row of facts and controls instead of a title that repeated the breadcrumb, every page's first row starts just under the top bar, and the gap under it is the same everywhere. The header keeps its tiles beside the name only while the name has room, wraps them under it otherwise, and no longer flips between the two at one width. On a phone the top bar's title no longer runs under the icons.
- **Compare opens the project's real pages**: a project's grade in a dimension view opens that project's own dimension page, and a principle (matrix cell, principle health or attention item) opens its findings scoped to that principle. Both make that project the selection, so every principle, file, folder, area and Fix first row on the page works, and Back returns to Compare.
- **Compare, calmer**: the duel and dimension views use the app's monospace and fewer sizes and colours, the dimension page picks its dimension from a launcher, and score tables sort by header. The fleet score's 30-day change sits small beside the score, project names and grade labels no longer cut off, summary cards keep their label on one line, and the direction map's points can be reached and opened from the keyboard.
- **Adding a standard no longer rebuilds every project**: each run's cached score now depends only on the standards it scored, and only on their scoring content, so creating, installing, renaming or rewording a standard rebuilds nothing; editing one rebuilds only the runs that scored it.
- **The Map opens faster on big repositories**: its git activity is read once and kept until a branch moves or a new run day appears.
- **Repositories shows the checked-out branch** beside a local project's path.
- **Quieter source builds**: running quodeq from a checkout shows a spinner instead of more than a hundred build lines, replays the output only on failure, and skips reinstalling packages when the lockfile has not changed.

### Fixes
- **Settings shows the AI provider and model again**: they were missing from the Evaluation group after a merge earlier in this release.
- **First run**: the welcome's and empty page's **disconnect** button works again, "1 source file" reads in the singular, the CLI's default model reads *(default)*, and the Overview's header line no longer leaves a lone dot when it wraps.
- **Screens refresh when a rebuild ends**: Compare and other screens no longer keep the old formula's scores after the rebuild finishes, and the rebuild strip no longer freezes on "0 of 8 projects" after the work is done.
- **Live evaluation**: a finished dimension keeps its grade in the live feed when you were on another screen as it landed, and a PR review running in CI names the repository it reviews.
- **Overview and run cards**: "latest" is the newest finished run, not a newer cancelled one; a past run's note says when it ran in words with **back to latest** as a button; and a run's grade word follows the score shown.
- **History**: switching between a run's tabs no longer leaves stale groups behind, the page no longer scrolls far past its panels, and a cancelled run with one dimension reads "1 dim".
- **Repositories**: a refresh that fails because the upstream branch was deleted or renamed says so, and every refresh error shows git's own output under the message.
- **Remote projects**: the read-only note uses the header's style, and the Map's breadcrumb shows the project's published name instead of its id.
- **Never stop a stranger's process**: `quodeq stop`, cancelling a run and the launch's stale-API cleanup act on a recorded PID only when it still belongs to quodeq, so a PID the system reused for another program is left alone, including on Windows. `nohup quodeq dashboard --no-open &` keeps running after the SSH session closes.
- **The Dock tooltip reads quodeq** instead of `python3.14` for pip, Homebrew and source installs on macOS.
- **A shared repository can no longer pass options to git**: a run's recorded commit could reach `git diff` as an option, so a collaborator could make the shared project's Overview overwrite a file on your machine (present since 1.13). Commits must now look like commit hashes, git is told where options end, and quodeq never runs git on a path a shared repository names. A shared archive may also unpack to at most 100 times its size, and publishing refuses a shared project tree that contains a link.
- **Security hardening**: without an API key the server only answers requests from this machine that name a local host, which stops DNS-rebinding pages. A shared repository can no longer make the Map run git on a path it names, requirement ids are length-capped and scanned before they reach a prompt, and symlinked standards in a shared clone are never followed. Tokens in repository addresses are masked in errors, the desktop self-update only accepts a DMG from a quodeq GitHub release, the project scan does not follow symlinked folders, and the assistant's tool errors never echo exception text.
- **Steadier internals**: an assistant turn that fails answers with an error instead of leaving the reply hanging, a failed write to a run's log no longer stops the job's output, and a failed score-cache write no longer leaves a half-finished transaction behind.

### Docs
- **The in-app Help matches 1.14**: the grade formula page is rewritten for the new editor and the v7 defaults; Standards explains settings living on this machine and sharing through the shared repository; Settings, Map, Overview, History, Repositories, the assistant and the command line pages follow the new screens and commands; Getting Started, Running Evaluations, Overview and AI Providers describe the first run and the model panel; the loading tips are up to date; and the README shows the 1.14 dashboard. The website's docs are built from the same pages.

## [1.13.1] - 2026-10-11

### Improvements
- **Help**: the Help page is restyled for reading. The text sits in a reading column, the section list is a hairline list with the current section marked, rows that open with a term render as definition lists, wide screens get an "On this page" list that follows your scrolling, and each section ends with previous and next links. Below 900px the section list becomes a tab strip.
- **Sidebar**: the footer lists Standards first, then Settings, then Help: what quodeq measures, then how the app behaves, then the docs.

### Fixes
- **Tips carousel**: the Q² tip shows the superscript instead of the raw HTML entity.

### Docs
- **The in-app help reads as documentation**: the pages are edited for readers who do not have the app open, and the website's docs are generated from them. Philosophy no longer describes the pre-1.13 grade formula and points to Why This Grade; AI Providers opens with the three ways to supply a model and all nine providers, says what to expect from local models, and folds the Copilot policy text into a note; Command Line & CI documents the environment variables a headless run reads, a minimal GitHub Actions job with `quodeq ci report` and its real flags, and that pull request reviews are GitHub only while cloning and SARIF work with any git host; Getting Started no longer repeats Quickstart; the Projects page and nav entry are named Repositories, like the tab; GitHub Access is Git Access; severity descriptions no longer set deadlines; and the name is written `quodeq` throughout. The URL validation error no longer implies GitHub is the only host.

## [1.13.0] - 2026-10-10

### Features
- **A grade that sees how widespread a problem is, and follows the model's judgment**: every principle is now scored per broken rule, weighted by the share of the project's files the rule touches. Compliance counts in the same unit, principles weigh by how much of the code they were observed on, and a principle with few observations is scored and marked as thin evidence instead of being left out. Each finding keeps the severity the model gave it. The standard now suggests a severity per rule in the checklist the model reads, and `.quodeq/standards-overrides.json` accepts a `severity` per requirement to change that suggestion for a project; the model decides the impact of each instance and says why when it departs. Every grade in every project changes with this release, and the Overview says so on runs scanned with the older formula. The grade is the model's: on the OWASP Benchmark it reads Critical or Poor with the models that rate injection as exploitable, and the benchmark page shows each model. The evaluation rules changed, so the next evaluation of every project re-analyzes all files once. Why This Grade and the grade formula editor explain the stages. A custom formula saved before this release is retired, since its constants were tuned for the old mechanics; the editor opens on the new defaults.
- **The Overview is ordered around what to do next**: hero cards, then the score history beside **where the findings live** (one row per real folder, the shared prefix shown once, the top five folders with a link to the full tree in Map), then the quality dimensions, then **fix first** (the requirements across the visible dimensions, critical first) and the files table. A standard switched on but never evaluated shows an empty dashed card that opens Evaluate. Long lists open on eight rows with a show-all footer. Every element is still clickable: a folder opens its findings, a requirement opens its findings in the By type view.
- **Compare rebuilt around the questions a comparison asks**: the fleet landing opens with a summary (fleet score and its 30-day change, size-weighted too, codebase size, violation density per 100 analysed files, critical findings, freshness and spread), then every project as a dot on a shared score axis that fits the scores, a direction map that fits the projects with dotted reference lines for "no change" and the fleet average, and a score matrix of small grade-coloured chips with the best and worst of each dimension outlined. Column headers rank the table. The head-to-head screen reads top to bottom: the verdict with whether the gap is bigger than the projects' run-to-run swing, a fairness strip that marks what weakens the comparison, gap sources and exposure side by side, a smoothed trend with the real runs behind it, a principle scatter with each side's biggest edges, and every score behind a pill. The dimension page is the fleet overview one level down, with one active project highlighted across the radar, the standings and the principle matrix. One hover reads in every theme, a row in the attention list opens its project's weakest dimension wherever you click, and charts no longer rebuild their geometry on every mouse move.
- **Repositories is one row per project**: name with its folder, score, files, last run, and, when a team repository is connected, location and sync. Each row carries the one action its state needs (publish, update, pull, or relocate for a missing folder); the rare ones sit in a menu. Column headers sort, newest run first by default. The server band with its status, invite and update sits on top of the table, a clone in progress is the first row, and subprojects are indented under their parent.
- **Evaluate, lighter and consistent**: the setup card opens with nothing preselected, the running screen shows a pulsing dot and a stop pill instead of a status badge, tiles count this run's new violations, changed files and the time used of its budget, and one bar carries details and console. The finished run settles into the same layout with a check mark. Runs the app did not start (the nightly, a PR review, a terminal or MCP run) are noticed within seconds, named by where they came from, read clearly on Evaluate and can be stopped safely; a PR review ends on a readable screen with a link to the pull request. The live findings open one thing at a time. A run whose time budget ran out with files still queued is now flagged as partial instead of reading complete, and the remaining files carry over to the next run.
- **A boot screen with the full logo and a tip to read**: the compass needle sways while the app boots, the first tip shows beside the logo and the screen stays long enough to read it; twenty more tips joined the rotation, half about the shared repository. Every other loader shows a quiet breathing logo.
- **The code widget names its file**: the code under a finding opens from an editor-style tab that shows the full path with the file name in bold and the line in the accent colour, the line range, and a copy-path button that confirms with a check.
- **The dimension page has trend arrows**: the title, the score and the critical and major chips show the change against the previous day, week or month, following the same picker and the same series as the Overview cards.
- **Live findings stay fast on big runs**: the dimension groups on Evaluate start closed and only open when you click them, several at once if you like. Each header shows its count and its critical, major and minor split, and marks the dimension being scanned. An open group only mounts the findings near the viewport, like the File and Principle pages, so a dimension with thousands of findings scrolls without lag, and findings reach the screen in batches of up to 100 ms instead of one render each. Above the groups, a ticker lists the latest 10 findings from any dimension as they arrive, newest on top. Hovering it pauses it and says how many are waiting. Clicking a finding pins it above the ticker with its detail open until you close it (up to 3 pins).

### Improvements
- **Help pages match the app**: every help page was checked against the component or string it describes, from where the evaluations repository is added to the assistant and terminal being on by default.
- **Faster diffs and projections, steadier runs**: a run diff reads each older run once instead of once per dimension, a scoring pass reads the installed standards once, a console tail no longer skips lines after an invalid byte, a job snapshot is never silently left unscored, and a report with a malformed principles entry still loads.
- **A strip says when scores are being rebuilt**: while a grade formula pass runs, or the warm-up rebuilds project summaries after an update, a one-line band under the top bar on every page shows what is running and how far along, "rescoring 412 of 1,980 runs" or "rebuilding scores 2 of 12 projects", and names the project being rebuilt. It stays for a moment when the work ends and offers a retry when a pass failed. Until now the count showed only beside the Apply button in Settings and the dimmed grades elsewhere gave no reason. The strip never blocks the page.
- **Switch project from the top bar**: the project name at the top left opens a searchable list of your projects (also on Cmd/Ctrl+P), most recently evaluated first, with each one's grade. It lists the team's remote projects too, tagged remote, unless you already have a local copy. Picking one keeps you on the page you were on.
- **The last known grade stays on screen while scores rebuild**: after a formula change or an update, the Overview and the project cards used to show a loading state with no number until the background rebuild reached the project. They now keep the grade the server last computed, dimmed and marked updating, until the new one lands. The rebuild after a formula change starts with every project's newest run, most recently active project first, so the grades you look at are rewritten early and the history fills in behind. Dismissing a finding now moves the Overview's headline score at once instead of after the refresh.
- **The Dismissed tab shows a dismissal at once**: a finding you dismiss anywhere is in the Dismissed tab the moment the dismiss succeeds, without a fetch of the whole list. The tab shows loading bars while its first fetch is in flight instead of "No dismissed findings". On the server, a dismissal records the run it was made from, and the listing looks the finding up in the newest run, then in that run, before walking the rest; the resolved detail is kept while nothing changes. An entry whose finding no run held any more cost a walk over every run on every open of the tab, measured at 5.9 seconds on a project with 382 runs; it now costs it once per change.
- **One judge for every run**: the grouped analysis mode is gone. It asked the model to rate every dimension in a single pass on a clean scan with a CLI provider, which made a clean baseline and the incremental runs after it two different judges now that the grade follows the model's rating. A clean scan runs each dimension over every file with the same prompt an incremental run uses. The Analysis mode setting and the `--no-consolidated` flag are removed; runs with an API provider and incremental runs were already per-dimension and do not change.

### Fixes
- **The Overview score matches Compare**: the two could differ by a tenth (8.9 against 8.8) because the browser rounded the average differently from the server and ignored the formula's dimension weights. The browser now rounds exactly like the server and applies the same weights.
- **A dimension page opened from Compare charts its own project**: opening another project's dimension from the matrix showed the selected project's score history and arrows; the page now loads the shown project's own history and the crumb names it.
- **The Evaluate button hides while a run is live**: the run chip already opens the running evaluation; the dimmed button beside it did nothing.
- **Evaluation buttons share the app's shape**: scan, view results, stop, details, console and close use the same corners, size and lowercase labels as the rest of the app.
- **Dismissing a finding never lowers its dimension**: a dismissal removed the finding's file from what the grade counts as observed, so a strong principle could lose weight in its dimension and pull the dimension down. Dismissed findings now add no penalty but stay observed, so a dismissal only ever raises the grade. Stored grades are recomputed once.
- **Finding cards link their references again**: the CWE, CISQ, SEI CERT and other reference links beside a finding's reason were missing on every run since 2026-09-29. The links were still attached, but with no text, so nothing showed. New findings are written with their labels again, and runs already on disk get theirs back from the stored reference or its url, with no re-run needed.
- **Detail pages keep their detail**: the File and Principle pages, and the reports and fix plans built from them, sometimes showed a finding's title with no detail text and no code, mostly while scores were updating. Those pages now render the rows their own `/compliance-detail` query returns instead of patching detail into the list payload's rows by identity: the query is keyed on what it asks for (run or as-of, dimension, scope), not on the `/scores` response it was fetched for, so a refetch of the list keeps the rows on screen and refreshes them in place. A finding whose detail is still loading shows a skeleton where its text and code go; one whose detail failed to load says so and retries. The report and fix-plan panes follow the page's data instead of printing the rows they were registered with, and the dimension page's report and fix plan now fetch the detail the eval defers before printing, as the run page's already did. On the server, concurrent `/scores` and `/compliance-detail` requests that miss the payload memo build it once.

## [1.12.2] - 2026-10-06

1.12.1 never reached PyPI: its publish stopped at the security audit. 1.12.2 is the same release with the fix below, and carries everything listed under 1.12.1.

### Fixes
- **Build dependencies**: patched `seroval` (critical advisory, pulled in by the React Query developer tools) and `source-map-js` (high, pulled in by the CSS and test tooling). Neither ships in the app's interface; the release audit now reports no vulnerabilities.

## [1.12.1] - 2026-10-06

### Features
- **Adding a project is one field**: `add project` on the Repositories tab opens a panel with one field that takes a git url or a local folder (`local folder` fills it from the picker) and nothing else; the reviewer and the standard live on Evaluate. A `more` menu holds the evaluations repository and import. The welcome is three cards, one per way in, and opens on first run and from Settings only. A project that lands, by an add or by a clone that finishes, becomes the selected card on Repositories; nothing moves you to another tab. Overview, Violations, Map and History show from the first project on, and Evaluate exists only for a selected project that has landed. (#1394, #1395)
- **The team's results arrive one by one, ready to open**: a shared project's card appears once its scores are fully computed, a placeholder stands in for each card still to come, and the strip says how many are ready ("loading results · 1 of 4 ready"). Opening a card lands on a ready Overview instead of a loading screen that could fail. (#1399, #1400)

### Improvements
- **The Overview no longer blocks at start**: after an update, or when a state folder was restored, the Overview of a large project was built on the request while the background warm-up rebuilt the same project; the request outlived the client's timeout and every retry started the work again, so the app looked stuck. The Overview and the shared list now answer at once with a pending state and fill in when the warm-up has the project. Measured on a 369-run project: 36 seconds and a timeout became three seconds to a loading state and 26 seconds until every project was warm. Every project still recomputes its score cache once after this update. (#1398, #1401)
- **Finding cards say when a finding changed**: on the File and Principle pages a card whose finding was re-reported by a newer run (a new title, moved lines) used to show only its title. It now says the finding changed and the page refreshes with the latest results. (#1402)

### Fixes
- **Reconnecting an evaluations repository** no longer fails with "Couldn't clone the shared repository" after a disconnect: the disconnect waits for the warm-up before removing the clone, and a removal that cannot finish never leaves the folder unreadable. (#1400, #1401)
- **A wiped or replaced state folder starts over**: the welcome's "skip for now" and a selected shared repository belong to the state folder, not the browser, so a fresh `~/.quodeq` shows the welcome instead of an Overview asking for a project the server does not have. (#1396, #1397)
- **Repositories**: an existing project is no longer hidden as "cloning" because its folder shares a name with a running clone, a project still cloning no longer opens "Couldn't load this project", and an address without a scheme such as `github.com/org/repo` is treated as a remote. (#1395, #1401)

## [1.12.0] - 2026-10-03

### Security
- **Provider keys stay off disk by default**: when no operating system keyring is available, an API key is no longer written to `.quodeq.env`. Export the provider's key variable (for example `ANTHROPIC_API_KEY`) in your shell, or set `QUODEQ_ALLOW_PLAINTEXT_KEY=1` to keep the previous owner-only file fallback. Settings shows which variable to export when a key cannot be saved. (#1310)
- **Hardening from self-evaluation**: the security and reliability majors quodeq reported on its own code are fixed: malformed request bodies answer coded 400s instead of 500s, parsing of metadata and model output is stricter, subprocesses carry timeouts, and every git subprocess runs with prompts disabled and a closed stdin so a clone can never hang on a password. (#1268, #1291, #1296, #1301, #1307, #1371)

### Features
- **A new welcome and a one-screen analyze**: the first run, `add project` and Settings open a welcome with two paths, a repository of your own or your team's evaluations repository. Analyze is one screen: paste a git url or choose a local folder, see the working copy quodeq keeps, who reviews it and which standard, then press scan and run. A git url is cloned as a background job with a progress bar; a ghost tile at the head of the Repositories list carries that progress while you look elsewhere, shows the reason if the clone fails, and the evaluation starts once the clone lands. A detected provider without a model asks for one before the run, and a project that cannot be evaluated is told why: a missing folder, a file instead of a folder, or a git url that still needs cloning. (#1372, #1374, #1379, #1384, #1389)
- **Join your team's results without a restart**: connecting an evaluations repository from the Repositories tab or the welcome runs as a background job with clone progress, the team's projects appear as soon as the connect finishes, and refresh and pull report their progress the same way. An invite text for teammates is one click away. (#1372, #1374)
- **GitHub access that tells the truth**: before any clone, connect or publish, quodeq probes the URL and reports whether it is reachable and with which credentials. A GitHub URL that needs credentials opens an access panel inside the app: sign in with GitHub, use the gh CLI token, paste a token, or configure git yourself. Settings gains a GitHub access block and Help a GitHub Access page. (#1371)
- **Fetch latest code from a project card**: project cards with a git remote get a third footer action. A clone quodeq manages resets onto its tracked branch; a folder you registered fast-forwards only from a clean tree. Refusals say why (uncommitted changes, diverged history, an evaluation reading the checkout). (#1380)
- **Numbers that only move with the code**: findings are scored by requirement code instead of the model's free-form type tag, so a paraphrase between runs no longer moves the score (grade algorithm version 3; every stored run's visible scores shift once on first read, by up to +0.8 on maintainability and -0.3 on performance). The Overview's CRIT and MAJ chips carry their change since the baseline run with the same arrow the score tile uses, and the fourth tile shows the density (violations per 100 files) under the ratio. History gains MAJORS and TYPES columns with deltas, and bar tooltips with criticals, majors and open types. The Violations tab gains a by-type view that lists each requirement type as open, closed or new, and dismisses a whole type in one action. The report opens with the same counts, and the `quodeq evaluate` summary line reads `dim: SCORE (N major, T open types, D per 100 files, C% coverage)`. (#1278, #1283, #1284, #1285, #1286, #1287, #1292, #1293, #1294, #1373)
- **Grade formula editor by scoring stage**: Settings > Grade formula is rebuilt as FORMULA, TYPES and DIMENSIONS tabs, with your own run's numbers next to each stage of the formula and the saved result for comparison. Saving no longer blocks on rescoring every run: the API answers at once, the UI shows "Rescoring N of M runs", and an interrupted rescore resumes on the next start. (#1261, #1290)
- **Accessibility standard**: a built-in WCAG 2.2 standard covering levels A and AA as applied to software by EN 301 549 (35 requirements, including the new 2.2 criteria), with detection hints for Android, iOS and web. It is off by default like Clean Architecture and DDD; turn it on with the eye icon in Standards. Standards now show their family and edition (`iso-25010`, `wcag-2.2`), and the Evaluate chip reads WCAG. (#1312, #1313, #1314)
- **History lists cancelled runs**: a cancelled run that scored at least one dimension shows its own grade and score, marked partial, instead of a blank row. (#1271)
- **Request cost in view**: every API response carries a `Server-Timing` header (evaluation.db opens, report reads, build time, cache hit or miss), the same numbers end the request line in the server log window, and `GET /api/debug/metrics` (same machine only) reports process memory and CPU, each in-memory cache's entries and approximate size, and requests per route over the last minute. (#1342)

### Improvements
- **Large projects: run list, overview and Compare in milliseconds**: the Projects list, the Overview, the trend, the run pages, the dimension pages and Compare are served from cached per-run rows instead of reopening `evaluation.db` and reparsing reports on every request, and Compare asks for every selected project in one request. Finding detail (`reason`, `context`, `snippet`) is loaded when a Principle, File or Finding page opens rather than shipped with every payload, which took the Overview's dashboard request from 10 to 34 MB on a large project down to its scores. Measured warm on a 234-run project: runs list 1016 to 41 ms, overview 1794 to 67 ms, Compare of three projects 1940 to 224 ms. Every project recomputes its cached scores once after this update. (#1265, #1266, #1267, #1302, #1306, #1309, #1311, #1356, #1359, #1360, #1361, #1362, #1363, #1364, #1365, #1366, #1367)
- **Standards edits apply at once**: cached scores are keyed on the compiled standards and the project's threshold overrides, so an edited standard or override shows in the dashboard on the next load instead of after the next evaluation. (#1353)
- **The app stays responsive during a run**: a poll tick no longer re-renders the whole app, polls pause while the window is hidden, pages stay mounted across tab switches and paint their frame before the heavy body, one loading line on the top bar replaces per-section dimming, the live feed sends one request per tick, History stays responsive and the running run's page picks up finished dimensions as they land. (#1260, #1298, #1321, #1322, #1323, #1324, #1325, #1329, #1334, #1382)
- **Map on large trees**: the layout is cached and computed in a worker, circle packs above 2000 nodes paint on one canvas with the SVG look (file icons, eased zoom, hover glow), padding scales with depth, and the Map fades in instead of popping. (#1326, #1327, #1330, #1331, #1332, #1333, #1335)
- **One path for live updates**: live progress and findings arrive over the run's event stream only; the polled path and its build flag are gone. The live feed streams violations only, through the same classifier as the console counts (dedup, quarantine, suppression), so the feed matches the heartbeat instead of showing ten times its count, and returning to the Evaluate tab mid-run opens the dimension being analyzed. (#1336, #1337, #1338, #1375, #1383, #1385, #1387)
- **A pocket of bad input no longer cancels the run**: binary files that wear a source extension are skipped before they are queued, and a failure streak in one dimension ends that dimension early but lets the next one start when the model is alive. A dimension that fails from its first file still stops the run. (#1369, #1370)
- **Generic catches at a fault boundary are compliant**: R-FT-7 no longer files every generic catch. One that re-raises, or that sits at a thread entry point, a loop iteration or a plugin callback and logs the error with its stack trace, passes. Visible on a clean scan. (#1264)
- **One spelling per vocabulary**: run states, job statuses, exit reasons, severities and grades are declared once and read leniently (legacy spellings such as `complete` and `canceled` still parse). The run list now reports `done` and `running` where it said `complete` and `in_progress`. (#1241, #1256, #1259)
- **Loading tips that teach**: the startup loader's rotating tips are rewritten to explain how quodeq reads code, and are easier to read. (#1243)

### Fixes
- **Dashboard errors no longer stick**: "Failed to load dashboard data" and "Couldn't load this project" used to park until a restart. Errored queries now retry, polling continues after the desktop window reports offline, the last accumulated payload is served while a running evaluation churns its version, and the Overview never claims a project with runs has no evaluations. (#1242, #1246, #1306, #1381)
- **Live findings on a fresh run**: the run's event stream now stays open while the runner creates the run directory, so findings appear from the first file instead of after closing and reopening the project. (#1368)
- **Standards**: renaming a custom standard was silently lost; the Standards table dropped the ISO family after the WCAG addition; a finding without a principle is graded under its requirement's principle; dimension page grades come from the grade tables instead of a stale eval-time header. (#1282, #1304, #1313, #1314)
- **History**: a deleted run leaves the table at once with a pending state, and the table shows real majors and types for finished runs. The reconnect button reports what it is doing. (#1300, #1308)
- **Import replace no longer loses the old project**: a same-UUID import with replace deleted the existing project before the new one was written. (#1247)
- **Onboarding detects a running Ollama**: the probe read a route that never existed. (#1295)
- **Map drill-up keeps the viz style**: going up a level after switching to galaxy no longer flips back to circle pack. (#1297)
- **Repositories tab**: header actions match the strip below them, and the top bar's sync hairline stops when you leave the tab. (#1377, #1378)
- **Second instance isolation**: the run index and score cache live under `QUODEQ_DIR`, so a test or second instance never reads the live app's runs. (#1389)
- **Self-evaluation majors**: the clean-architecture, usability, performance and maintainability majors quodeq reported on its own code are fixed, 70 findings across four runs. (#1244, #1247, #1295, #1296, #1299, #1310)

## [1.11.0] - 2026-09-22

### Features
- **GitHub Copilot**: use Copilot for evaluations and assistant chat, with account model discovery, streamed responses, and session resume. Setup reports organization MCP policy blocks clearly instead of continuing an evaluation that cannot run. (#1213, #1228, #1230)
- **Built-in macOS menu bar**: enable the menu bar icon from Settings without installing a separate app. Launching the dashboard from a DMG offers to move it to Applications. (#1147, #1148)
- **Cached results follow file moves**: unchanged files moved to another directory can reuse their previous evaluation when the file name and test/production role still match. Changes in detected project language also preserve cached results. Existing caches migrate automatically, with migration and index building running in the background at dashboard startup. (#1155)
- **Dismissals survive refactors**: moving code to a different line no longer brings a dismissed finding back. An exact match for the same requirement and code in another file is automatically dismissed and removed from the score; it remains visible in the Dismissed tab and can be restored. Restored code stays eligible for findings until you dismiss it again. (#1165, #1226)
- **Deployment-aware evaluations**: declare single-host or distributed deployment in the project profile to tailor scalability findings. Loopback-only applications also receive fewer inappropriate transport-encryption findings, while outbound connections remain checked. (#1211, #1229)
- **Provider launch commands**: choose a different executable or wrapper for CLI evaluations in Settings, with inline validation before starting a run. (#1127, #1129)
- **Provider key storage**: save API keys through the backend using the operating system keyring when available, with a local configuration-file fallback. (#1160)

### Improvements
- **Faster dashboards and large histories**: project lists, score comparisons, live progress, and bulk dismissal actions do less repeated file and database work. Bounded caches and log views reduce memory growth during long sessions. (#1138, #1144, #1158, #1180, #1192, #1194)
- **Better use of evaluation time**: after the initial scout checks provider health, all available subagent slots launch. Dimensions with the largest remaining backlog run first, with time reserved for the remaining dimensions. (#1173, #1174, #1182, #1232)
- **More useful findings**: models get one repair attempt when a finding is missing its source snippet, and grounded findings are retained when only their severity value is malformed. (#1216, #1224)
- **Clearer score context**: dimension cards and CLI grades include violations per 100 files; CLI output also shows violation and major counts. Reports preserve the model's original violation-type tag. (#1172)
- **Maintainability defaults**: use a six-parameter threshold, 60-line functions, and complexity 15, while retaining the 300-line file threshold. The changed thresholds trigger a fresh maintainability evaluation on the next run. (#1190)
- **Keyboard and screen-reader access**: improve dialog focus, keyboard navigation, chart and map descriptions, control names, and announcements. Destructive bulk actions and workspace operations have clearer confirmations. (#1151, #1203)
- **Clearer failures**: provider setup, evaluation options, standards imports, terminals, and shared-repository operations report more useful errors. Failed setting changes are surfaced instead of appearing saved. (#1151, #1197)

### Fixes
- **Consistent source scope**: evaluations and the setup wizard count Git-tracked files consistently and explain how many untracked files are excluded. Projects outside Git retain the filesystem-based scan. (#1207, #1225)
- **Live findings and history**: dismissing a finding no longer breaks the live view; pending reports are distinguished from empty results; progress counts actual findings; completed dimensions can be opened before the whole run finishes. (#1163, #1219, #1220, #1221)
- **Dashboard controls**: restore the theme toggle, correct score-history colors and chart height, and refresh new or starred standards in the evaluation picker without reloading. (#1134, #1137, #1196, #1204, #1205)
- **More resilient state handling**: recover more safely from malformed metadata, unavailable browser storage, failed asynchronous requests, and concurrent database access. (#1153, #1169, #1170, #1212, #1215)
- **Security hardening**: protect desktop launch tokens, redact repository credentials and internal error details, validate download destinations and repository inputs, and escape untrusted text in generated PR comments. (#1152, #1160, #1162, #1166, #1171, #1223)

## [1.10.1] - 2026-08-28

### Fixes
- **Local analyses no longer stop mid-run**: on thinking-capable local models (Gemma 4, Qwen 3.x) served by Ollama, hidden reasoning could loop indefinitely, time out call after call, and trip the failure-streak breaker with "incomplete dimensions" partway through a run. Thinking is now genuinely disabled for local providers (the previous knob was silently ignored by Ollama), which also makes every local call dramatically faster, seconds instead of minutes. The assistant on local models gets the same treatment.
- **Runaway generations are bounded**: local model calls carry a default output budget of 8192 tokens (QUODEQ_MAX_OUTPUT_TOKENS overrides it, 0 disables it), so a degenerate generation ends at the budget instead of burning the whole call timeout. A capped response is retried on the next run, nothing is silently lost.
- **Honest context-size handling on Ollama**: QUODEQ_CONTEXT_SIZE cannot reach a model behind Ollama's OpenAI-compatible endpoint, which ignores per-request context settings. Quodeq now warns once and points at OLLAMA_CONTEXT_LENGTH, and the model-timeout hint no longer recommends a setting that cannot work there.

## [1.10.0] - 2026-08-27

### Features
- **Compare tab**: every analyzed project ranked on one screen. A scope score with its 30-day delta, fleet-wide violations and compliance, the spread between your best and worst project, and a needs-attention strip ranked by consequence, three cards up front and the rest behind an expand toggle. The projects table reads one line per project: score, the 30-day trend as a spark line, violations split by severity, compliance ratio, and freshness with a commits-behind count; clicking a name opens the project. The tab appears once two projects have runs and follows the standards you have enabled, exactly like the Overview, refreshing the moment you toggle one.
- **Score matrix**: every score at a glance, projects by dimensions, each cell a chip in its grade color. Per column the best score wears a solid border and the worst a dashed one, and clicking a column header re-ranks the fleet by it. A cell jumps straight into that project's own dimension screen, and columns that do not fit the panel distribute into stacked groups instead of scrolling. The dimension drill-down repeats the grammar one level deeper, projects by principles, with cells opening that project's principle page.
- **Head-to-head duel**: the duel button picks any two projects (a scope of exactly two goes straight in) and lays them out side by side: the gap in plain words, mirrored per-dimension bars, both score trends on one time axis with the 30-day window shaded, a shape radar, and every shared principle difference on screen at once. Each side keeps a stable identity color chosen away from the grade colors, so a line is a name, not a judgement.
- **Remote projects join the fleet**: with a shared repository connected, its published projects rank alongside local ones, tagged remote. They count toward the scope score, appear in the attention strip and the matrices, and can duel local projects; a project you also have locally shows once, local prevailing.
- **Cross-project jumps**: standings, principle cards and matrix cells inside Compare open that project's own dimension or principle page, and back returns you to where you were, your selected project untouched. Map drill-downs and violations sub-tabs join the same navigation stack, and clicking a breadcrumb navigates while holding it opens the sibling menu.
- **Staleness that means something**: a fleet row says how many commits a project is behind its last scan, not just how old the scan is, and rows refresh themselves the moment a run completes.

### Improvements
- **Loading shows the page's shape**: the Overview, History, Violations and Compare load behind skeletons that reserve the real layout instead of a spinner, project switches hold the placeholder until the content is ready, and the startup screen keeps its background, rotates one-line tips every five seconds, and fades out over the finished page.
- **Readable text everywhere**: interface text colors now clear WCAG contrast floors across all theme and mode combinations.
- **Compare help**: the Help tab explains the fleet view, the matrices, the drill-downs and the duel.

### Fixes
- **Dismissals from Compare stick**: dismissing a finding reached through a Compare drill-down applies to the project that owns the finding, wherever you came from, with a regression table covering every dismissing route.
- **Windows text encoding**: the git call behind the commits-since-scan counter reads its output as UTF-8 explicitly, so a Windows machine with a legacy codepage cannot corrupt it.

## [1.9.1] - 2026-08-24

### Features
- **Startup no longer waits on the cache rebuild**: upgrading invalidates every project's cached scores, and that rebuild used to happen while you watched. It now runs in the background from the moment the server starts, so the projects list answers immediately. Projects still being computed show a pending grade placeholder and fill themselves in, and the project you open jumps the queue.
- **Loading screens say what they are doing**: a wait longer than a few seconds now shows a rotating tip and a progress strip naming the project being prepared and how many are left, instead of a spinner with no end in sight.

### Improvements
- **Loading screen layout**: the tip sits under the logo with more room around it, the progress bar anchors to the bottom of the screen and finishes full before it disappears, and the logo holds steady instead of drifting. Tips are shuffled per launch, so a slow start does not replay the same order.
- **Help content**: the help pages catch up with recent releases. What happens after an update, time budgets as a hard cap, the exit reasons a run can report, the scope gate badge, the declared trust model and pattern suppression rules are all documented now, and the tips rotation grew from six entries to ten, each backed by something the help actually says.
- **Dependencies**: the OpenAI SDK moves to 3.0.0, verified against every provider call site Quodeq makes. nanoid is bumped to clear a build-time advisory, and packaging is kept current.

### Fixes
- **Startup hang after upgrading to 1.9.0**: the first launch after the upgrade could sit on the loading spinner forever while the backend burned CPU for minutes. Three things went wrong together. The post-upgrade rebuild ran once per piled-up request instead of once for all of them, the spinner had no way out once its retries were exhausted, and two concurrent first-opens of a fresh score cache could delete the database out from under a live connection. The rebuild is now shared by every request waiting on it, and a load that still fails offers a Retry button, keeps retrying quietly on its own, and recovers when the backend comes back.
- **Projects with nothing finished**: a project whose runs were all cancelled or still running now gets its fallback grade prepared like any other, instead of waiting on a summary that was never going to arrive.

## [1.9.0] - 2026-08-06

### Features
- **Declared trust model**: a project can state its own threat model in `.quodeq/project-profile.json`, and findings that the model excludes are capped instead of counted against you. A single-user tool bound to loopback no longer collects majors for cross-tenant attacks it cannot suffer. Network exposure is only ever read from the file you write, never guessed from your manifests, so nothing is waived without you declaring it.
- **Deterministic requirement checkers**: framework imports, entity imports and config reads are now checked by code instead of inferred by the model, so those requirements give the same answer on every run.
- **Suppression pattern rules**: a suppression can match a pattern instead of a fixed file and line, so a decision you already accepted survives the code being moved or renamed. Pattern rules count in scoring, not only in the findings list.
- **Partial results survive a dying provider**: when the provider fails mid-run the dimensions that already finished are kept instead of the run being discarded, and Quodeq stops respawning agents into a provider that is already gone.
- **Exit reasons in plain words**: a run that stopped early says why on the evaluate screen, with a hint on what to do about it, instead of showing a bare status.
- **Score provenance**: a history point says when it came from a partial scan, and an Overview grade says when it came from a tuned formula, so a number you did not expect is explainable from the screen.
- **Near-miss requirement IDs**: a finding whose requirement ID is slightly off is folded onto the right requirement instead of being quarantined out of your score.
- **Translation-ready interface**: every screen, the help pages and backend error messages now come from a string catalog instead of being hardcoded. English is still the only language shipped, but adding another no longer means touching the components.

### Improvements
- **Dates and numbers stop following the OS**: on a machine set to another language, dates and numbers inside the English interface were rendered in that language. They now follow a single locale, so one screen no longer mixes two.
- **Faster drill-in**: the findings list on principle detail is virtualized, finding payloads no longer ride along in browser history, and the explorer's dimension data is cached, so coming back from a principle or a file renders from cache instead of refetching behind a full-screen loader.
- **Feedback while a page renders**: a detail page that takes a moment to appear now leaves the current page up with a slim progress bar rather than painting nothing, so a click never looks ignored. Cards react to the press in the same frame.
- **Local models**: the read timeout scales with the number of subagents, so a heavily parallel local run no longer times out waiting on its own queue.
- **Architecture**: the internal layering was reworked so domain rules, storage and the API no longer reach into each other, with an import checker that keeps it that way. No behavior change on its own, but the class of bug listed below is much harder to reintroduce.
- **Dependencies**: pydantic is declared explicitly and runtime dependency ranges are bounded, so an install cannot quietly pick up an incompatible version.

### Fixes
- **Time limits**: an explicit time limit is now a hard cap. It no longer resets each time a dimension launches, the watchdog no longer cuts short a run that is draining its final results, and a run stopped by the deadline reports that it hit the time limit rather than FAILED or a user cancel.
- **Inflated grades on high-volume principles**: the severity floor no longer overrides the volume ceiling. A principle carrying hundreds of minor findings and no major ones was scored by the floor alone, which hid the volume entirely. Runs you already scanned re-derive their grades on first read, so a stored grade no longer disagrees with a fresh rescore or appears to change on its own after a dismissal.
- **Restore all**: restoring every dismissal asks for confirmation first, so one click can no longer wipe a project's dismissal history.
- **Skipped dimensions**: a run that skipped dimensions no longer reports a clean completion, and a dry run that finished normally is no longer reported as truncated.
- **Stale Overview scores**: accumulated rows cached before the partial-dimension guards landed were served forever. They are now flushed on the next read, so an Overview stuck on old numbers recovers without a rescan.
- **Relaunching the dashboard**: starting Quodeq while it is already running now brings the open window to the front instead of racing it, no longer kills the healthy instance, and a corrupt PID file no longer takes the launch down with it.
- **Reconnecting**: the interface now looks for the backend on the ports Quodeq actually binds, so a window whose server moved can follow it, and the disconnected notice appears on every route instead of leaving a spinner that never resolves.
- **Navigation**: drilling into a principle or a file keeps the source tab you were on.
- **Symlinked project directories**: a project directory reached through a symlink is still skipped for safety, but Quodeq now says so and names the link, its real target and the fix, instead of silently rendering the project as empty.
- **Security**: path containment on the API routes goes through one recognized barrier, the dimension name is validated against the installed set before it reaches a path, response bodies are bounded in bytes as well as in seconds, and operator-controlled inputs are no longer treated as external ingress.
- **Malformed project files**: an unreadable or pathological manifest, profile or per-project config degrades to safe defaults instead of failing the scan. Deeply nested JSON and TOML were the case that got through.
- **Waivers that came back**: a downgraded finding keeps its marker across cache replay and across the report's JSON round trip, so a finding capped once does not silently return as a major.

## [1.8.1] - 2026-07-29

### Features
- **Live feed**: findings from a run that never finished (cancelled, failed, or killed) now show up as new on your next scan instead of being hidden as carried over. Only runs that actually completed mark their findings as carried forward.

### Improvements
- **Readable times on the evaluate screen**: elapsed times and budgets read in human units, so a long run shows `4h 15m 12s` instead of `255:12` and a budget shows `10m` instead of `10:00`.

### Fixes
- **Evaluate screen clocks**: the ELAPSED tile and the progress footer now share one clock anchored to the server, so the two no longer disagree on screen, the footer is no longer blank until the first poll, and a skewed clock on your machine cannot throw the tile off. Per-dimension elapsed now comes from the run's own state transitions instead of being inferred from file timestamps.
- **Overview grades**: hidden standards no longer move the numbers you see. The hero grade letter and the project card grade are both derived from the standards you left visible, so the headline, its letter, and the card agree.
- **Stale scores after a run**: opening a project's scores while a scan was still running could freeze a partial set of dimensions in the cache, leaving the Overview on raw scores while the dimension pages showed the dismiss-adjusted ones. Partial results are no longer cached or persisted.
- **Multi-module projects**: repos whose root belongs to no detected subproject keep their full source tree instead of dropping every file outside a subproject. Kotlin Multiplatform repos were scanning zero files.
- **Android detection**: projects that declare the Android Gradle plugin through a version catalog alias are now recognized as Android.
- **Terminal**: clicking a link in the terminal opens it in your browser, instead of a warning dialog whose OK button did nothing.
- **Security**: the evaluations route rejects repo paths outside the project, credential stripping in URLs runs in linear time on hostile input, and the remote-repo check no longer treats any URL merely containing github.com as remote.

## [1.8.0] - 2026-07-29

### Features
- **Standards visibility**: choose per project which standards count. The selection now lives with the project on the server instead of in the browser, so it survives reloads, and the AI assistant honors it everywhere: hidden standards drop out of its scores, findings, overviews and standards list, and hidden dimension names stay out of its error messages. Standard ids now match case-insensitively across the standards and scan surfaces.
- **Live feed shows what's new**: findings carried over from previous runs are now marked at the source, and the live feed can show only findings that are new to the current scan. A new Evaluation section in Settings holds the preference, and the feed disclosure explains when carried-over findings are hidden.
- **Evaluate screen redesign**: new setup and running cards with estimate placeholders while sizes compute, a heads-up toast when the scan comes back clean, better spacing and tag contrast, dimension cards that use wide screens, and View results jumps to the evaluated project.
- **Toolbar redesign**: a jump-bar address in the topbar with run-aware chrome.

### Improvements
- **Loading and transitions**: one loader per route, loaders stay inside the content area (sidebar counts no longer jump), the Overview shows a loading skeleton on project switch, chart placeholders hold their height, empty states stay stable through the first-run load, and Violations, Map and History render real error states with a working Retry.
- **Severity consistency**: one severity vocabulary across the app, so severity chips always sum to the violation total (unknown severities fold into minor in summaries).
- **Live progress for grouped runs**: a consolidated run reports one real progress row (files taken, evidence tally, elapsed, active agents) instead of per-dimension rows stuck at 0%.

### Fixes
- **Evaluation pipeline audit**: cancelling a just-started job no longer errors, completed dimensions show their real elapsed time instead of 0:00, report writes are atomic so a mid-write read cannot drop a dimension, discarded runs stop resurfacing in the evaluations list, the live findings feed works for index-served full scans, and the run budget is plumbed end to end so the budget bar can render.
- **Effective settings tell the truth**: Settings, the Evaluate header, and the start payload now agree on what a run actually uses; the wizard's time limit (including unlimited) reaches the server; unlimited (0) propagates to the scan subprocess; cloud provider API keys are exported to the scan subprocess.
- **Countdown and post-run state**: the countdown hides when the run ends, binds to the running job's own budget so changing Settings mid-run cannot alter it, scores refresh as soon as an evaluation completes, and live-findings polling stops once the run is terminal.
- **Job lifecycle**: a server restart marks running jobs "lost" instead of "failed", and a transient error during cancel no longer drops a still-running job.
- **Run ordering**: dimensions run in the order you selected them.
- **History and Overview agree**: runs started without a prescan appear in both, so a pinned finished run no longer lands on "No evaluations yet"; fetch failures render an error state with Retry instead of claiming there are no evaluations.
- **Explorer**: a not-yet-ready report shows "Report not ready" instead of a fake clean report, and a slow earlier request can no longer park another run's findings under the current header.
- **API hardening**: scan, logs and overrides routes reject invalid path segments, and path containment checks were tightened.
- **Terminal**: the selected tab is remembered across drawer close and reopen.
- **UI details**: the breadcrumb's current item navigates back to its level, long stat values stay inside their tiles, the live feed copy button targets just the file label, and the evaluate screen describes the time budget as one total for the run.

## [1.7.3] - 2026-07-27

### Features
- **Multi-session terminal**: run up to 6 shell sessions as tabs, each its own shell with its own history. Sessions live server-side, so they survive page reloads and closing the drawer; closing a tab kills that shell. With a single session the tab strip stays out of the way and a + in the header opens the second.
- **Terminal panel redesign**: the terminal gets its own header with a working copy button, session tabs, and a status bar showing the shell, session count, working directory and the localhost-only sandbox note.
- **Assistant panel redesign**: new header with the Quodeq mark, project name and a model chip that jumps to Settings; tappable suggestion cards in the empty state; avatars and a thinking indicator in the transcript; a card-style composer with auto-grow and a proper send button.
- **Terminal colors**: terminal output now renders with a full 16-color ANSI palette that follows the app theme in light and dark.

### Improvements
- **Faster assistant skills on local models**: providers without native tool-calling now receive the full tool catalog and exact action payload formats in the prompt instead of guessing them one failed attempt at a time. Suggested actions appear only on views where they can actually run.
- **Drawer chrome**: the shared drawer header is gone; each panel carries its own controls, with a compact Assistant/Terminal switcher when both are open.

## [1.7.2] - 2026-07-26

### Features
- **Quarantine visibility**: reports record how many findings were quarantined, and the live scan counters net suppressed findings out instead of over-counting them.
- **Terminal file links**: cmd-click a file path or URL in the terminal to open it.
- **Remote repositories without local projects**: shared repositories now appear on the Repositories page even when you have no local projects yet.

### Improvements
- **Performance**: hot-path fixes found by self-evaluation (memoized stats, an O(n^2) MST, a hoisted backfill query), and the Overview reuses one run walk across as-of score selections.
- **Assistant streaming**: CLI providers stream text as deltas instead of whole messages, so replies render as they arrive.
- **Security scanning**: CodeQL and Snyk run on pull requests and releases, with results uploaded to GitHub code scanning.
- **Help**: the shared repository workflow is documented in the in-app help.

### Fixes
- **Dismiss consistency**: dismissing, restoring, or deleting a finding now affects scores the same way on every surface. The dashboard reconciles immediately (including assistant-applied dismissals), the Overview grade refreshes on its own, and the CLI matches the UI.
- **Stale data on project switch**: switching projects loads clean instead of briefly showing the previous project's numbers.
- **Cancelled runs**: a cancelled run no longer shows as running while it drains.
- **Exports**: the zip size cap applies to the compressed archive, and the uncompressed cap matches the import guard.
- **Evaluation countdown**: hidden when the time limit is unlimited.
- **Drawer inputs**: the terminal and assistant inputs autofocus when their tab opens.
- **Terminal**: a NUL byte in the /open path fails soft instead of erroring.
- **Analysis isolation**: the claude scan subprocess runs with --strict-mcp-config so local MCP configuration cannot leak into evaluations.
- **Maintainability scoring**: non-dict JSONL lines are guarded and grade thresholds are frozen against accidental mutation.
- **Assistant reliability**: the assistant database uses SQLite synchronous=NORMAL, avoiding stalls without risking corruption.

## [1.7.1] - 2026-07-23

This is the first 1.7 release to reach PyPI and Homebrew. 1.7.0 shipped desktop builds but a flaky publish-time test blocked its PyPI and Homebrew steps, so pip and Homebrew users install 1.7.1. The full 1.7 feature set is below; there is no change to shipped code between 1.7.0 and 1.7.1 beyond the release-plumbing fix.

### Features
- **Shared evaluations (share the code)**: publish a project's results to a git repository your team controls, and browse teammates' evaluations read-only from the same Repositories page. Publishing is additive and syncs only completed runs. There is no server, the shared repo is your own git remote and auth is your existing git access.
- **Semantic precedent matching**: when you dismiss a finding, Quodeq now recognizes the same issue on later runs by meaning, not just by exact fingerprint, so a false positive you already judged stops coming back after small code or wording changes.
- **Assistant on remote projects**: the AI assistant now opens on shared (remote) projects in read-only mode, so you can ask it to explain scores and dig into findings on a teammate's results without a local copy. Its mutating actions stay disabled there.
- **Projects page redesign**: local and shared projects live in one unified, filterable list with sync-state badges (local / published / remote) and a single badge system that follows your theme in light and dark.
- **Grade formula responsiveness**: changing a grade threshold invalidates the cached scores immediately, so the dashboard reflects your new formula without a manual refresh.
- **macOS Help menu**: a native Help menu on the desktop app.

### Improvements
- **Projects page**: newly added projects appear instantly, a location filter (local / published / remote), and cards flip to their published state right after publishing instead of waiting for a background refresh.

### Fixes
- **Security**: hardened error-detail handling in confidentiality checks, tightened SSRF path and shell-argument handling on clone, and a batch of security and reliability findings from the audit.
- **Terminal on remote projects**: the terminal now opens on shared projects (it is a local shell and never needed a project mutation path).
- **Remote project title**: the topbar and sidebar show the project name (clickable) on remote projects instead of only the page name.
- **Shared repositories**: consistent online and offline project states, safe clone cleanup on Windows with read-only git objects, shallow-clone handling for online repos, and correct sidebar tabs, empty states, and navigation for shared selections.
- **Onboarding**: the setup-incomplete state resolves correctly once a project has runs.
- **Release plumbing**: a shared-publish idempotency test monkeypatched the clock with a fixed two-value iterator, which a legitimate rebase-retry under a git push/fetch race could exhaust (StopIteration) and fail the publish workflow non-deterministically; the test now uses a monotonic clock.

## [1.7.0] - 2026-07-23

### Features
- **Shared evaluations (share the code)**: publish a project's results to a git repository your team controls, and browse teammates' evaluations read-only from the same Repositories page. Publishing is additive and syncs only completed runs. There is no server, the shared repo is your own git remote and auth is your existing git access.
- **Semantic precedent matching**: when you dismiss a finding, Quodeq now recognizes the same issue on later runs by meaning, not just by exact fingerprint, so a false positive you already judged stops coming back after small code or wording changes.
- **Assistant on remote projects**: the AI assistant now opens on shared (remote) projects in read-only mode, so you can ask it to explain scores and dig into findings on a teammate's results without a local copy. Its mutating actions stay disabled there.
- **Projects page redesign**: local and shared projects live in one unified, filterable list with sync-state badges (local / published / remote) and a single badge system that follows your theme in light and dark.
- **Grade formula responsiveness**: changing a grade threshold invalidates the cached scores immediately, so the dashboard reflects your new formula without a manual refresh.
- **macOS Help menu**: a native Help menu on the desktop app.

### Improvements
- **Projects page**: newly added projects appear instantly, a location filter (local / published / remote), and cards flip to their published state right after publishing instead of waiting for a background refresh.

### Fixes
- **Security**: hardened error-detail handling in confidentiality checks, tightened SSRF path and shell-argument handling on clone, and a batch of security and reliability findings from the audit.
- **Terminal on remote projects**: the terminal now opens on shared projects (it is a local shell and never needed a project mutation path).
- **Remote project title**: the topbar and sidebar show the project name (clickable) on remote projects instead of only the page name.
- **Shared repositories**: consistent online and offline project states, safe clone cleanup on Windows with read-only git objects, shallow-clone handling for online repos, and correct sidebar tabs, empty states, and navigation for shared selections.
- **Onboarding**: the setup-incomplete state resolves correctly once a project has runs.

## [1.6.1] - 2026-07-12

### Fixes
- **Evaluation lifecycle**: Cancel + Discard now reliably removes the run, even when the scan process is wedged and never updates its own status. Deleting an evaluation honors exactly the action you chose in the dialog instead of inferring one. The watchdog stops the entire process tree of a stuck scan, so no orphaned workers keep burning CPU in the background.
- **Scoring consistency**: the dashboard, Overview, History, and the project card now share one run-eligibility rule, so they agree on the score, including projects whose only runs are failed or still in progress. In-progress runs no longer stand in for a chart bucket, day highlight, sparkline point, or visible-standards average; trends only reflect finished results.
- **History**: score history groups runs by your local calendar day instead of the UTC date, so late-evening runs no longer show up under tomorrow.
- **Evaluation cards**: a run's card always shows the project the run belongs to, and a background run finishing no longer hijacks the project you are currently viewing.
- **Jobs**: the job store is isolated per dashboard instance, and pruning/eviction only ever touch that instance's own entries.
- **Assistant**: applying or rejecting a suggested change is now atomic, discarding a workspace is guarded against racing with an in-flight apply, and leaked write worktrees, branches, and stale sessions are garbage-collected automatically.
- **Terminal**: reconnecting after sleep or a dropped socket resets the view instead of duplicating scrollback, input is blocked while disconnected so keystrokes are not silently lost, and the busy indicator reflects the real connection state.
- **Grade formula**: a formula apply that only partially succeeds now reports which projects kept stale grades instead of failing silently.
- **UI polish**: the standard detail view uses the logo loading screen instead of a plain text fallback.

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
