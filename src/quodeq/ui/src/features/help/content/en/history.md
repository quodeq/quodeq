## History & Trends

The **History** tab is your project's quality timeline. Every completed run lives there with its grade, score, and delta from the run before.

### The run list

- **Grade and score** for each run.
- **Delta** against the previous run, so you can spot regressions immediately.
- **Majors and types**: the run's blocking findings (criticals plus majors) and its open types (distinct requirement codes with an open finding), each with the change against the previous run over the dimensions both runs scored. Down is good for both.
- **Run metadata** model, sub-agent count, scope, branch, duration.
- **Archived tag**: a run that quodeq stored compressed to save space carries an *archived* tag. Opening it restores it first, so the run page shows *restoring archived run…* for a few seconds. Nothing in its grades or findings changes. See **Storage** in the Settings help section.
- **Report only tag**: a run whose findings were removed to save space (Settings › Storage, *Keep the findings of archived runs for*). Its grades and reports stay, so it opens at once and still counts in the trend; its findings cannot be searched or rescored.
- **Tombstones** deleted runs leave a marker so the trend stays continuous.

### The selected run

Selecting a run shows it beside the list: its grade and score, its criticals and majors against the run it was compared with, and tabs for its dimensions and for the findings it found new or fixed. The up and down arrow keys move the selection through the runs.

The **Dimensions** tab shows each dimension the run scored as a card, the same card as on the Overview, weakest first. Each card has the dimension's score, grade and severities in that run, and under them what the run changed in it: the findings it found new and the findings it fixed, each with how many of them were criticals and majors. A dimension the run was not compared on says *not compared*. Click a card to open that dimension as of the run.

### The trend chart

A small chart above the list plots each run's own score over time. Hover a bar to read the run's score, criticals, majors and open types; click to highlight that run.

### Group the Overview chart by day, week, or month

The *score history* chart on the **Overview** groups runs per day by default. Use the selector in the chart header to switch to **Week** or **Month**. Each bar aggregates the runs of one period, tooltips carry the period label, a week being named by its dates, such as *23 – 29 Mar 2026*, rather than a week number, and your choice is remembered across sessions.

The chart appears from the second evaluation, whatever the grouping. If all your runs fit inside a single week or month, it draws that one bar all the same, with the min, max and average of the bars on show in its header, and the selector stays so you can go back to a finer grouping.

```figure
component: ScoreGroupingFigure
caption: The score history header. The dropdown groups bars by day, week, or month.
```

### The run page

**Open run** opens the run on its own page, laid out like the **Overview** but for that one run. The header shows the run's score ring and grade, when it ran, and where it came from: the origin (a nightly, a pull request, the app or the CLI), the model, the commit, how long it took and how many files it analysed. Its tiles (violations with their severities, pass rate, per 100 files and critical per 1,000) each show their change against the run it was compared with, the same run the History log counts new and fixed findings against. A run rescored by a newer grade formula says so under the title, as does the number of findings that were suppressed.

Above the header, *since the previous run* counts the findings the run found new and the ones it fixed, and the rule types that appeared or went away. The dimensions follow as the Overview's cards, weakest first, each with what the run changed in it. At the bottom, *Fix first* sits beside the run's folders and files (areas are measured for today only, so a past run has none).

Everything on the page opens as of the run and read-only: a tile, a requirement, a folder or a file opens its findings as they were in that run, and a card opens the dimension as of the run. The sidebar keeps **History** selected, and Back returns to the run page.

The oldest run with a set of dimensions has nothing to compare with: its tiles show no changes, the since line says so, and every card says *not compared*.

### Partial and cancelled runs

A cancelled run that finished some of its dimensions is listed with its own grade for those dimensions, reads *cancelled · 4 of 6* in the list, and says under its score how it stopped and which dimensions did not finish. Its run page shows only the dimensions it scored. It is not part of the score history, so the Overview chart leaves it out, and the next run reuses the work it finished instead of analysing those files again.

> **Comparing across time**
>
> To see how a dimension moved, open a run, then open the dimension from its card: the dimension page shows that run and the score history around it.
