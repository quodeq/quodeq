## Projects

The **Projects** tab is your home base. Every codebase you evaluate becomes a project with its own grade, score, and run history.

### What each row tells you

- **Grade and score** from the latest run, on a 0 to 10 scale. After an update the grade can show a pulsing placeholder for a while: the score is recomputing in the background and lands on its own.
- **File and line counts** of the analyzed scope.
- **Last run timestamp** and the model that produced it.
- **Setup state**: projects with an interrupted onboarding show a *Resume setup* action.

### What you can do

| Key | Value |
| --- | --- |
| Select project | Open it. Goes to Overview if it has runs, otherwise Evaluate. |
| + Add project | Open the wizard at Repo Scan to add another codebase. |
| Import project | Restore a project from a previously-exported file. |
| Resume setup | Pick up an interrupted wizard with the same draft. |
| Relocate | Update the local path if the repo moved on disk. |
| Export | Download the run findings as JSON. |
| Delete | Remove the project and all its runs. Not reversible. |
| Publish / update | Send completed runs to the connected shared repository. |
| Pull local copy | Import a teammate's shared project into your local list. |

With a shared repository connected, every card also carries a *LOCAL*, *PUBLISHED*, or *REMOTE* badge, and a location filter appears above the list. The **Shared Repository** help section covers the whole workflow.

### Sub-projects and monorepos

You can evaluate a subdirectory of a repository as its own project by setting **Scope** in the wizard or in *Evaluate*. Each scoped run becomes a distinct project; Quodeq detects the parent-child relationship and groups them in the list so you can compare quality across packages.

> **Wiping the slate**
>
> Projects, runs, and findings live under `~/.quodeq`. Delete that directory and Quodeq starts fresh, including the welcome wizard.
