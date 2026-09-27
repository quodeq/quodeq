## History & Trends

The **History** tab is your project's quality timeline. Every completed run lives there with its grade, score, and delta from the run before.

### The run list

- **Grade and score** for each run.
- **Delta** against the previous run, so you can spot regressions immediately.
- **Majors and types** the run's open majors (critical plus major) and open requirement types, each with the change against the previous run. Down is good for both.
- **Run metadata** model, sub-agent count, scope, branch, duration.
- **Tombstones** deleted runs leave a marker so the trend stays continuous.

### The trend chart

A small chart above the list plots each run's own score over time. Two thinner lines follow it on their own scale: majors (dashed) and open types (dotted). Hover a bar to read the run's score, majors and open types; click to highlight that run.

### Since the baseline

Under the chart, the since-baseline panel follows the highlighted run: which run it is compared with, how many files changed in between, the majors delta, the types closed and opened, and the new and resolved findings in that scope. **see findings** opens them. Shared repositories have no baseline here.

### Group the Overview chart by day, week, or month

The *score history* chart on the **Overview** groups runs per day by default. Use the selector in the chart header to switch to **Week** or **Month**. Each bar aggregates the runs of one period, tooltips carry the period label, and your choice is remembered across sessions.

If all your runs fit inside a single week or month, the chart suggests a finer grouping instead of drawing one lonely bar.

```figure
component: ScoreGroupingFigure
caption: The score history header. The select groups bars by day, week, or month.
```

### Run detail and the navigator

Clicking a run opens its **Run Detail** page: the same shell as Overview but locked to that single run. From there, the run navigator at the top lets you step **previous / next / latest** without going back to the list. Drill into any dimension and the Explorer keeps the run id, so you stay anchored to that snapshot.

### Partial and cancelled runs

Cancelled runs that kept their partial findings appear with a *partial* tag. They count for trend purposes but the Run Detail page makes the partial state obvious so you do not over-interpret it.

> **Comparing across time**
>
> The Run Detail navigator is the fastest way to A/B compare. Open the dimension you care about in run N, hit *previous*, and watch the principle scores shift.
