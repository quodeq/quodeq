## Compare

The **Compare** tab ranks every local project side by side. It appears in the sidebar once at least two projects have been evaluated; with fewer there is nothing to rank.

### Reading the fleet

- **Stat cards** the scope-wide picture: average score with its 30-day delta, violations by severity, compliance percentage, and the spread between the best and worst project.
- **Needs attention** the actionable summary, ranked by *consequence*: how bad a score is, weighted by project size and staleness. Each card names the reason (weakest dimension, decline over 30 days, code moved since the scan, thin coverage) and links straight into the relevant dimension. The marker colour is the project's grade colour.
- **Projects table** one line per project: rank, score with tier, the 30-day delta, violations, the compliance-to-violations ratio, and the last evaluation. A dimmed delta means every run predates the 30-day window; it then shows the change at the last evaluation instead. Sorting is by score, and the toggle flips best-first / worst-first.

### Staleness means the code moved

A grade is *stale* when commits landed after the run that produced it, not when the run is merely old. A 45-day-old grade with no commits since is current; a same-day grade with commits behind it is provisional. The commit count shows in the row's expansion and in the last-column tooltip. When the working copy can't be inspected (online projects, moved paths), an age check stands in.

### Row expansion

Click a row to expand it in place: severity split, the score trend as a line (oldest to newest, coloured by the latest grade), coverage, the commit count since the scan, one chip per dimension, and the jump to the project's overview. Any number of rows can stay expanded, so two projects' details can sit side by side. Projects that were never evaluated collapse into a single line with a show toggle.

### The dimension drill-down

Click any dimension chip or board row to see that dimension across the scope:

- **Standings** projects ranked on this dimension. Clicking a row opens *that project's own screen of the same dimension*; the browser back button returns here, and your selected project never changes.
- **Radar** overlays the leader, the trailer, and the scope average across the dimension's principles. Hovering a standings row draws that project's shape on top.
- **Principle cards** the scope average per principle with the leader and trailer named. The small bars follow the standings order and carry the standings rank, so the same slot is the same project in every card. Clicking a bar, or the leader/trailer entry, opens that project's own principle page.

### Head-to-head

Any two projects can go head to head: expand a row and pick an opponent under **compare with…**. The duel view shows per-dimension gaps, principle differences for shared dimensions, and both trends on one chart; gaps always read left minus right. When the scope holds exactly two projects, a **compare these two** shortcut also appears in the header.

### Scope

The project picker narrows every number on the screen to a chosen subset; **flagged** selects only the projects currently needing attention. Each project's numbers respect its own enabled standards, exactly as its Overview does, so a dimension nobody enables never appears here.

### Remote projects

When a shared repository is connected, its published projects join the fleet as ordinary rows tagged **remote**. They rank, count toward the scope score, appear in the attention strip, and can duel local projects. A published project you also have locally is the *same* project, matched exactly as the Projects screen matches it, and your local copy prevails: one row, no remote duplicate. Only projects that exist solely in the shared repository appear as remote rows. Opening a remote row switches to its shared, read-only view; deep links into principle pages stay local-only.
