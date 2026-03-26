# Accumulated Evaluation Panel Redesign

## Summary

Redesign the `acc-eval-panel` hero section (used in both the Dashboard accumulated view and the Explorer dimension view) to use golden segment proportions, circular score gauges, and a simplified stat layout.

## Design Decisions

### Layout: Golden Split (38.2% / 61.8%)

- **Left column (38.2%):** SVG circular gauge showing the score, with the letter grade inside
- **Right column (61.8%):** Stat blocks stacked vertically

### Score Circle (B1 variant)

- SVG ring gauge where the filled arc represents the score out of 10
- Inside the circle: numeric score (large, e.g. "7.8") with letter grade below (smaller, colored, e.g. "B+")
- Trend badge sits below the circle
- No "/10" denominator displayed

### Stats: Two-stat layout (Dashboard)

Drop the raw compliance count — it's derivable from violations × ratio. Show only:

1. **Violations** — count + severity tags (critical / major / minor)
2. **Compliance Ratio** — displayed as "1 : N" with "compliance per violation" label

### Stats: Compact layout (Explorer)

The Explorer dimension panel has additional data. Layout:

1. **Violations** — count inline with severity tags on the same row
2. **Ratio / Files / Principles** — three mini-stats in a horizontal row

### Ratio Presentation

The ratio is always `1:N` (compliance per violation). No progress bars or donut charts — just the numeric ratio. A split proportion bar was considered but rejected because the ratio can be anything from 1:1 to 1:20+, making a bounded bar misleading.

## Components Affected

### `AccumulatedHeroSection` (`AccumulatedOverviewPanel.jsx`)

Current structure:
- `.acc-eval-panel` → `.acc-eval-top` (label + date) → `.acc-eval-hero` (grade chip + score + trend) → `.acc-eval-stats-grid` (3 stat blocks)

New structure:
- `.acc-eval-panel` → `.acc-eval-top` (label + date) → `.acc-eval-golden` (golden split container)
  - `.acc-eval-circle-col` (38.2%): SVG gauge + trend badge
  - `.acc-eval-stats-col` (61.8%): violations block + ratio block

### `DimensionOverview` (`ExplorerPage.jsx`)

Current structure:
- `.acc-eval-panel.acc-eval-panel--compact` → `.acc-eval-top` (title + fix plan btn) → `.acc-eval-hero` (chip + score) → `.acc-eval-stats-grid` (5 stat blocks)

New structure:
- `.acc-eval-panel.acc-eval-panel--compact` → `.acc-eval-top` (title + fix plan btn) → `.acc-eval-golden` (golden split)
  - `.acc-eval-circle-col` (25%): smaller 80px SVG gauge (no trend)
  - `.acc-eval-stats-col` (75%): violations row (count + inline tags) + mini-stats row (ratio, files, principles)

### Sub-components to add/modify

- **`ScoreCircle`** — new component: renders the SVG ring gauge with score + grade inside. Props: `score`, `grade`, `size` (default 120, compact 80), `colorClass`
- **`StatBlock`** — keep existing, used for violations and ratio
- **`SeverityTags`** — keep existing
- **Remove:** `.acc-eval-grade-chip`, `.acc-eval-score-row`, `.acc-eval-score`, `.acc-eval-score-denom` classes (replaced by circle)

### CSS changes (`dashboard.css`)

- Remove: `.acc-eval-hero`, `.acc-eval-grade-chip`, `.acc-eval-score-row`, `.acc-eval-score`, `.acc-eval-score-denom` rules
- Add: `.acc-eval-golden` (flex container), `.acc-eval-circle-col`, `.acc-eval-stats-col`
- Update: `.acc-eval-panel--compact` modifiers for smaller circle and tighter spacing
- Keep: `.acc-eval-panel`, `.acc-eval-top`, `.acc-eval-stat-block`, `.acc-eval-tags` (reused as-is)

## Visual Specs

### Full panel (Dashboard)
- Circle: 120×120px, 8px stroke, score color from `scoreColorClass()`
- Score text: 30px bold
- Grade text: 13px semibold, colored (same as ring)
- Trend badge: below circle, existing `TrendBadge` component
- Violations stat-val: 18px
- Ratio stat-val: 22px, "1 : N" format
- Ratio sublabel: 11px muted, "compliance per violation"

### Compact panel (Explorer)
- Circle: 80×80px, 6px stroke
- Score text: 20px bold
- Grade text: 10px semibold
- Left column: 25% width (smaller ratio than full panel due to extra stats)
- Violations: 16px count, inline severity tags
- Mini-stats row: 14px values, 9px labels

## Testing

- Verify both panels render correctly with real data
- Check edge cases: 0 violations (ratio becomes "—"), missing grade, missing score
- Responsive: panels should stack vertically below 480px
