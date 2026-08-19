## Command Line & CI

The dashboard is one subcommand of the `quodeq` CLI. The rest run headless: scripted evaluations, pull-request reviews, and machine-readable exports.

### Commands

| Key | Value |
| --- | --- |
| quodeq | Launch the dashboard. Same as `quodeq dashboard`. If one is already running, it focuses the existing window instead of starting a second server. |
| quodeq evaluate &lt;repo&gt; | Run an evaluation without the UI. Takes a path or URL. |
| quodeq review | Evaluate your current branch and post the findings as a PR review. |
| quodeq export sarif | Convert a finished evaluation to a SARIF file. |
| quodeq ci report | Post evaluation results on a PR from inside a CI pipeline. |

### Evaluate flags worth knowing

- `--dimensions` a comma-separated subset instead of all dimensions.
- `--branch` and `--scope` analyze a branch (via a temporary worktree) or a subdirectory.
- `--time-limit` total seconds for the run; 0 means unlimited. Quodeq scores whatever finished in time.
- `--clean-scan` ignore cached findings and re-analyze every file.
- `--evidence-only` collect findings but skip scoring.

### Reviewing pull requests

`quodeq review` detects the PR for your current branch, evaluates only the files changed against the base branch, and posts the findings as a review through the `gh` CLI. `--dry-run` builds the review without posting; `--pr` targets a specific number.

In a pipeline, split the steps: `quodeq evaluate --diff-from origin/main` analyzes the changed files (evidence only, no scores; grading a partial diff would mislead), then `quodeq ci report --from-evidence` posts the result using a GitHub token.

### SARIF export

SARIF is the findings format GitHub code scanning and GitLab understand. Add `--sarif findings.sarif` to an evaluation, or convert one afterwards with `quodeq export sarif`. Use `--min-severity` to drop noise. Code snippets stay out of the file unless you pass `--with-snippets`; they leave the machine when uploaded.

> **Every command documents itself**
>
> `quodeq <command> --help` prints the full flag list, including defaults.
