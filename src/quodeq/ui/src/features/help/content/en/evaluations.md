## Running Evaluations

The **Evaluate** tab is where you start, watch, and finish a run. The same screen handles configuration, live progress, and the result hand-off.

### Inputs

| Key | Value |
| --- | --- |
| Local path | `/path/to/your/project` |
| GitHub URL | `https://github.com/org/repo` |
| SSH path | `git@github.com:org/repo.git` |

### Options

- **Dimensions** which quality dimensions to include. Hidden dimensions in *Standards* are skipped automatically.
- **Branch** which git branch to analyze. Defaults to the repo default.
- **Scope** a subdirectory to focus on, e.g. `packages/frontend`. Useful for monorepos.
- **Sub-agents** how many parallel agents run. Higher is faster, costs more.
- **Time budget** a hard cap on run length. When the timer expires the run stops, whatever completed is scored, and the remaining files carry over to the next run.

### Who reviews this run

The strip at the top of the card names the repository, the scope (*whole project*, or the subfolder you picked) and the model, written as provider, model and effort. Clicking the model cell opens *Who reviews this run* in place: the providers as pills (one that is not installed cannot be picked), then the selected provider's model and effort. The confirm button, **use** followed by the model's name, saves that choice, exactly as choosing it in **Settings** would, and closes the panel; it does not start a scan. **all model settings** opens Settings for everything else, such as API keys. Escape or a click outside closes the panel without saving. Until a model is chosen the model cell is marked and the scan button stays disabled, with *pick a model to start* beside it.

### A project's first run

On a project that has never been evaluated, the card starts with every dimension selected and the time limit set to **no limit**, so the first run reads the whole project once. Untick dimensions or set a limit before you press **scan** if you want less. Later runs start from your usual time limit with the dimensions you pick.

### A remote project

A project someone else published (a *REMOTE* card on Repositories) keeps its **Evaluate** tab, but an evaluation only runs on a local copy, so the tab opens on a card saying the project is remote, with the three steps to its grades: *pull*, *review* and *score*. **pull local copy** brings the project and its runs to this machine; the card says *downloading…* while it works, and if a local project already has that name it asks whether to **pull as a copy**. When the copy lands and you are still on the card, the app selects the local copy and stays on Evaluate, where its first run starts as any first run; if you moved away meanwhile, a toast says the local copy is ready, with **evaluate** to open it. A failed pull shows its reason on the card, with **try again**, or in a toast when you had left. See *Pulling a project* in the **Shared Repository** help section.

### Excluding paths

Add a `.quodeqignore` file at the scan root to keep fixture, vendored, or generated code out of every evaluation. One glob per line, relative to the root; naming a directory excludes everything under it. Exclusions apply everywhere files are collected, on top of the built-in skips (`node_modules`, `dist`, dot-directories).

### Incremental and clean scans

By default, quodeq carries findings for unchanged files forward and re-evaluates only files that have changed since the last run. This keeps subsequent scans fast without losing coverage.

A quodeq update that changes a built-in standard re-analyses every file of that dimension once, on its next run. Version 1.16 does this for Security, whose hardcoded-credentials rule changed.

The **Clean scan** toggle forces a full re-analysis of every file. Use it after a big refactor, when you change standards, or whenever you want a fresh start. The toggle has three states:

- **Off (default)** incremental behavior. Unchanged-file findings are reused; only changed files are re-evaluated.
- **Once** the next scan runs clean. The toggle resets to Off automatically after that run completes.
- **Permanent** every scan runs clean until you turn the toggle off. Stored in `localStorage` so it persists across sessions.

The Clean scan toggle is available both on the Scan form (before you start) and on the Re-evaluate card (after a run finishes).

### What you see while it runs

The Evaluate tab streams a live phase indicator (detect → analyze → collect → score → report), an active provider badge, a countdown against your time budget, and a feed of findings as the agents discover them. Click any finding in the feed to jump straight to its file context, even mid-run.

### Cancelling a run

Hit **Cancel evaluation** any time. You will be asked whether to **keep partial findings** (everything collected so far is scored as a partial run) or **discard** (the run is dropped). Completed dimensions are always scored on cancel; dimensions in flight stop where they are.

### How runs end

Not every run ends with a clean *done*, and the run names its exit reason:

- **Done** every requested dimension completed. A run that skipped dimensions is not reported as done.
- **Time limit reached** the budget expired. Completed work is scored and the remaining files carry over to the next run.
- **Cancelled** you stopped it. Kept partials are scored; discarded ones are dropped.
- **Failed** the provider died mid-run. Findings collected before the failure are kept, and quodeq stops instead of retrying into the same error.

### When it finishes

When a project's first run finishes cleanly and you are still on **Evaluate**, the app moves to the project's **Overview**, where its first grades land. Otherwise the result card offers **View results**, **Evaluate again**, or **Back to project**. Each completed run is added to history with its grade, score, and delta from the previous run.

> **Re-evaluating an existing project**
>
> From any project you can launch a fresh run on the same scope. Subsequent runs are added to *History* so you can track quality over time without losing previous results.
