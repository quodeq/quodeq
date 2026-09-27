## Overview

The **Overview** tab is a project's landing page: the accumulated quality picture plus the fastest routes into the details.

### Accumulated scores

Overview shows the latest scored result for each dimension, even when those results come from different runs. Evaluate security today and maintainability tomorrow; both appear side by side, each card labeled with the run that produced it. To inspect a single run instead, open it from *History*.

### Header stats

- **Majors** critical plus major findings that are still open. The badge is the change since the baseline run; down is good. The hint counts the criticals.
- **Open types** distinct requirement codes with at least one open finding. The hint says how many types closed since the baseline. Fixing every finding of one code closes a type; fixing some of them does not move this number.
- **Score** the overall number and grade, with a delta against the previous run.
- **Density** open findings per 100 files read, summed over the dimensions shown. The hint is coverage: files read over source files.
- **Footer** compliance, the compliance to violations ratio, and the raw violations total with severity badges. Click the total, or a badge, to open a project-wide findings view filtered to that severity. Click compliance to browse the compliant findings.

### Since baseline

Under the header, the panel names the baseline run and the current run with their commits, how many files changed between them, the majors delta, the types closed and opened, and the new and resolved findings in the changed files. When no commit was recorded, or the tree had uncommitted changes, the counts cover all files and the panel says so. An unchanged tree gets one sentence instead of numbers. **see findings** opens the findings that are new in that scope, as one list across dimensions, labelled with its scope and count (the first 200 per dimension when there are more).

### Panels

- **Score history** runs over time, groupable by day, week, or month. See *History & Trends*.
- **Dimension scores** one bar per dimension. Click a bar to open that dimension in the Explorer.
- **Dimension cards** a gauge per dimension with principle detail. Click a card to open the Explorer anchored to the run behind the score.
- **Violations by file** the worst files, sorted by severity. Click a row to open the file detail.

### The report

The **Report** button in the top bar renders the whole overview as a Markdown report in the side pane, ready to download and share outside Quodeq. The report leads with the same numbers as the header (majors, open types, score, density), then the since-baseline summary, and keeps the raw violations total in its summary at the end.
