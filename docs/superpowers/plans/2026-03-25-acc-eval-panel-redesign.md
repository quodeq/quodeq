# Accumulated Evaluation Panel Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the acc-eval-panel hero section to use a golden-split layout with an SVG score circle and simplified two-stat display.

**Architecture:** Replace the linear hero+grid layout with a two-column golden-split (38.2%/61.8%). Left column holds a new `ScoreCircle` SVG component; right column holds violations + compliance ratio stats. The compact Explorer variant uses a 25%/75% split with extra stats (files, principles).

**Tech Stack:** React (JSX), CSS custom properties, SVG for the circular gauge

**Spec:** `docs/superpowers/specs/2026-03-25-acc-eval-panel-redesign-design.md`

---

### Task 1: Create the ScoreCircle component

**Files:**
- Create: `src/quodeq/ui/src/components/ScoreCircle.jsx`

This is a pure presentational component that renders an SVG ring gauge with score and grade text inside.

- [ ] **Step 1: Create ScoreCircle component**

```jsx
// src/quodeq/ui/src/components/ScoreCircle.jsx
import { scoreColorClass } from '../utils/formatters.js';

const GRADE_STROKE_VAR = {
  'grade-top':    'var(--color-grade-top-text)',
  'grade-high':   'var(--color-grade-high-text)',
  'grade-mid':    'var(--color-grade-mid-text)',
  'grade-low':    'var(--color-grade-low-text)',
  'grade-bottom': 'var(--color-grade-bottom-text)',
  'grade-none':   'var(--color-text-muted)',
};

/**
 * SVG ring gauge showing score and grade.
 * @param {number|string} score  - numeric score (0-10)
 * @param {string}         grade - letter grade (e.g. "B+")
 * @param {number}         size  - pixel diameter (default 120)
 */
export default function ScoreCircle({ score, grade, size = 120 }) {
  const n = parseFloat(score);
  const fraction = isNaN(n) ? 0 : Math.min(n / 10, 1);
  const colorClass = scoreColorClass(score);
  const strokeColor = GRADE_STROKE_VAR[colorClass] || 'var(--color-text-muted)';

  const strokeWidth = size >= 100 ? 8 : 6;
  const radius = (size / 2) - (strokeWidth / 2) - 2;
  const circumference = 2 * Math.PI * radius;
  const dashoffset = circumference * (1 - fraction);

  const scoreFontSize = size >= 100 ? 30 : 20;
  const gradeFontSize = size >= 100 ? 13 : 10;

  return (
    <div className="score-circle" style={{ width: size, height: size, position: 'relative', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke="var(--color-border)" strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2} cy={size / 2} r={radius}
          fill="none" stroke={strokeColor} strokeWidth={strokeWidth}
          strokeDasharray={circumference} strokeDashoffset={dashoffset}
          strokeLinecap="round"
        />
      </svg>
      <div style={{ position: 'absolute', textAlign: 'center', lineHeight: 1.2 }}>
        <div style={{ fontSize: scoreFontSize, fontWeight: 700, color: 'var(--color-text)', fontVariantNumeric: 'tabular-nums' }}>
          {isNaN(n) ? '—' : score}
        </div>
        {grade && (
          <div style={{ fontSize: gradeFontSize, fontWeight: 600, color: strokeColor, marginTop: 2 }}>
            {grade}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it renders in isolation**

Open the dashboard in the browser and temporarily import `ScoreCircle` in `AccumulatedOverviewPanel.jsx` to confirm it renders. Remove the temporary usage after confirming.

- [ ] **Step 3: Commit**

```bash
git add src/quodeq/ui/src/components/ScoreCircle.jsx
git commit -m "feat(ui): add ScoreCircle SVG gauge component"
```

---

### Task 2: Add golden-split CSS layout rules

**Files:**
- Modify: `src/quodeq/ui/src/styles/dashboard.css` (lines 3-122, the acc-eval section)

Replace the hero and stats-grid rules with golden-split layout classes. Keep `.acc-eval-panel`, `.acc-eval-top`, `.acc-eval-label`, `.acc-eval-date`, `.acc-eval-stat-block`, `.acc-eval-stat-label`, `.acc-eval-stat-value`, `.acc-eval-tags` untouched — they're still used.

- [ ] **Step 1: Remove old hero and compact rules**

Remove these CSS rules from `dashboard.css`:
- `.acc-eval-hero` (lines 37-42)
- `.acc-eval-grade-chip` (lines 44-49)
- `.acc-eval-score-row` (lines 51-55)
- `.acc-eval-score` (lines 57-63)
- `.acc-eval-score-denom` (lines 65-69)
- `.acc-eval-trend .trend-badge-*` (lines 71-72)
- `.acc-eval-panel--compact .acc-eval-hero` (line 74)
- `.acc-eval-panel--compact .acc-eval-grade-chip` (line 75)
- `.acc-eval-panel--compact .acc-eval-score` (line 76)
- `.acc-eval-panel--compact .acc-eval-score-denom` (line 77)

- [ ] **Step 2: Replace the stats-grid rules with golden-split layout**

Replace `.acc-eval-stats-grid` and its responsive media queries with:

```css
/* ── Golden-split layout ─────────────────────────────── */

.acc-eval-golden {
  display: flex;
  gap: 24px;
  align-items: center;
}

.acc-eval-circle-col {
  flex: 0 0 38.2%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.acc-eval-stats-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.acc-eval-ratio-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-left: 4px;
}

/* ── Compact variant (Explorer dimension overview) ──── */

.acc-eval-panel--compact .acc-eval-golden { gap: 16px; }

.acc-eval-panel--compact .acc-eval-circle-col {
  flex: 0 0 25%;
  gap: 6px;
}

.acc-eval-panel--compact .acc-eval-stats-col { gap: 12px; }

.acc-eval-panel--compact .acc-eval-stat-value { font-size: 1.1rem; }

.acc-eval-mini-stats {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.acc-eval-mini-stat {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.acc-eval-mini-stat-label {
  font-size: 0.65rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.acc-eval-mini-stat-value {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

/* ── Responsive ─────────────────────────────────────── */

@media (max-width: 480px) {
  .acc-eval-golden {
    flex-direction: column;
    align-items: stretch;
  }
  .acc-eval-circle-col {
    flex: none;
    align-self: center;
  }
}
```

- [ ] **Step 3: Confirm CSS file is syntactically valid**

Run: `cd src/quodeq/ui && npx vite build --mode development 2>&1 | head -20`
Expected: no CSS parse errors

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/styles/dashboard.css
git commit -m "feat(ui): replace acc-eval hero CSS with golden-split layout"
```

---

### Task 3: Rewrite AccumulatedHeroSection with golden-split layout

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/components/AccumulatedOverviewPanel.jsx` (lines 38-84)

- [ ] **Step 1: Update imports**

Add `ScoreCircle` import at the top of the file (after the existing imports):

```jsx
import ScoreCircle from '../../../components/ScoreCircle.jsx';
```

- [ ] **Step 2: Replace StatBlock, SeverityTags, and AccumulatedHeroSection**

Replace lines 38-84 (the `StatBlock`, `SeverityTags`, and `AccumulatedHeroSection` functions) with:

```jsx
function SeverityTags({ severity }) {
  return (
    <div className="acc-eval-tags">
      {(severity?.critical || 0) > 0 && <span className="severity-tag critical">{severity.critical} critical</span>}
      {(severity?.major || 0) > 0 && <span className="severity-tag major">{severity.major} major</span>}
      {(severity?.minor || 0) > 0 && <span className="severity-tag minor">{severity.minor} minor</span>}
    </div>
  );
}

function AccumulatedHeroSection({ accumulated, scoreDelta, lastDate }) {
  const summary = accumulated?.summary;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-label">Accumulated Evaluation</span>
        {lastDate && <span className="acc-eval-date">Last evaluated {lastDate}</span>}
      </div>
      <div className="acc-eval-golden">
        <div className="acc-eval-circle-col">
          <ScoreCircle
            score={summary?.numericAverage}
            grade={summary?.overallGrade}
            size={120}
          />
          {scoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={scoreDelta} showLabel={false} />
            </div>
          )}
        </div>
        <div className="acc-eval-stats-col">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{summary?.totalViolations || 0}</span>
            <SeverityTags severity={summary?.severity} />
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance Ratio</span>
            <span className="acc-eval-stat-value">
              {complianceRatio(summary?.totalViolations || 0, summary?.totalCompliance || 0)}
              <span className="acc-eval-ratio-label">compliance per violation</span>
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
```

Note: `StatBlock` is removed — it was only used here. The stat markup is now inline since each block has slightly different content.

- [ ] **Step 3: Verify the dashboard renders**

Open the dashboard in the browser. The accumulated panel should show the golden-split layout with circle on the left, two stats on the right.

- [ ] **Step 4: Commit**

```bash
git add src/quodeq/ui/src/features/dashboard/components/AccumulatedOverviewPanel.jsx
git commit -m "feat(ui): rewrite AccumulatedHeroSection with golden-split and ScoreCircle"
```

---

### Task 4: Rewrite RunHeroSection and StatsGrid in RunOverviewPanel

**Files:**
- Modify: `src/quodeq/ui/src/features/dashboard/components/RunOverviewPanel.jsx` (lines 1-57, 154-189)

The single-run overview panel uses the same hero pattern (`acc-eval-hero`, `acc-eval-grade-chip`, etc.) plus a `StatsGrid` with 6 stats (violations, compliance, ratio, files, principles, dimensions). Apply the golden-split layout with the circle, and use the compact-style mini-stats for the extra stats.

- [ ] **Step 1: Add ScoreCircle import**

Add at the top of `RunOverviewPanel.jsx`:

```jsx
import ScoreCircle from '../../../components/ScoreCircle.jsx';
```

- [ ] **Step 2: Rewrite RunHeroSection (lines 154-189)**

Replace the `RunHeroSection` function with:

```jsx
function RunHeroSection({ dashboard, selectedRunId, stats }) {
  const { runSummary, runScoreDelta, runTopFiles, runUniquePrinciples } = stats;
  return (
    <section className="acc-eval-panel panel">
      <div className="acc-eval-top">
        <span className="acc-eval-date">{dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId)}</span>
        {(dashboard?.dimensions || []).some((d) => (d.violations?.length || 0) > 0) && (
          <CopyButton
            label="Fix plan"
            onClick={() => {
              const allViolations = (dashboard.dimensions || []).flatMap(
                (d) => (d.violations || []).map((v) => ({ ...v, dimension: d.dimension }))
              );
              copyToClipboard(buildDimensionPlanFromViolations(dashboard?.selectedRun?.dateLabel || formatRunId(selectedRunId), allViolations));
            }}
          />
        )}
      </div>
      <div className="acc-eval-golden">
        <div className="acc-eval-circle-col">
          <ScoreCircle
            score={runSummary.numericAverage}
            grade={runSummary.overallGrade}
            size={120}
          />
          {runScoreDelta !== null && (
            <div className="acc-eval-trend">
              <TrendBadge delta={runScoreDelta} showLabel={false} />
            </div>
          )}
        </div>
        <div className="acc-eval-stats-col">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <span className="acc-eval-stat-value">{runSummary.totalViolations || 0}</span>
            <div className="acc-eval-tags">
              {(runSummary.severity?.critical || 0) > 0 && <span className="severity-tag critical">{runSummary.severity.critical} critical</span>}
              {(runSummary.severity?.major || 0) > 0 && <span className="severity-tag major">{runSummary.severity.major} major</span>}
              {(runSummary.severity?.minor || 0) > 0 && <span className="severity-tag minor">{runSummary.severity.minor} minor</span>}
            </div>
          </div>
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Compliance Ratio</span>
            <span className="acc-eval-stat-value">
              {complianceRatio(runSummary.totalViolations || 0, runSummary.totalCompliance || 0)}
              <span className="acc-eval-ratio-label">compliance per violation</span>
            </span>
          </div>
          <div className="acc-eval-mini-stats">
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Files</span>
              <span className="acc-eval-mini-stat-value">{runTopFiles.length}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Principles</span>
              <span className="acc-eval-mini-stat-value">{runUniquePrinciples}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Dimensions</span>
              <span className="acc-eval-mini-stat-value">{runSummary.dimensionCount || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Remove the old StatsGrid function (lines 16-57)**

Delete the `StatsGrid` function — its content is now inlined in `RunHeroSection`.

- [ ] **Step 4: Verify the Run Overview panel renders**

Navigate to a specific run in the dashboard. The panel should show the golden-split layout with circle, violations + ratio stats, and files/principles/dimensions as mini-stats.

- [ ] **Step 5: Commit**

```bash
git add src/quodeq/ui/src/features/dashboard/components/RunOverviewPanel.jsx
git commit -m "feat(ui): rewrite RunOverviewPanel with golden-split and ScoreCircle"
```

---

### Task 5: Rewrite DimensionOverview compact panel in ExplorerPage


**Files:**
- Modify: `src/quodeq/ui/src/features/explorer/components/ExplorerPage.jsx` (lines 44-107)

- [ ] **Step 1: Add ScoreCircle import**

Add at the top of `ExplorerPage.jsx`:

```jsx
import ScoreCircle from '../../../components/ScoreCircle.jsx';
```

- [ ] **Step 2: Rewrite DimensionOverview function (lines 44-75)**

Replace the `DimensionOverview` function with:

```jsx
function DimensionOverview({ data, stats, onNavigate }) {
  const { evalData, runId, dateLabel, allViolations } = data;
  const { overallGrade, severityCounts, totalCompliant, topFiles, uniquePrinciples } = stats;
  return (
    <section className="acc-eval-panel acc-eval-panel--compact panel">
      <div className="acc-eval-top">
        <div style={columnStyle}>
          <span className="explorer-dimension-title">{evalData.dimension}</span>
          {runId && <span className="acc-eval-date">{dateLabel || runId}</span>}
        </div>
        {allViolations.length > 0 && (
          <CopyButton
            label="Fix plan"
            onClick={() => copyToClipboard(buildDimensionPlanFromViolations(evalData.dimension, allViolations))}
          />
        )}
      </div>
      <div className="acc-eval-golden">
        <div className="acc-eval-circle-col">
          <ScoreCircle
            score={overallGrade?.score?.replace('/10', '')}
            grade={overallGrade?.grade}
            size={80}
          />
        </div>
        <div className="acc-eval-stats-col">
          <div className="acc-eval-stat-block">
            <span className="acc-eval-stat-label">Violations</span>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
              <span className="acc-eval-stat-value">{allViolations.length}</span>
              <div className="acc-eval-tags">
                {severityCounts.critical > 0 && <span className="severity-tag critical">{severityCounts.critical} crit</span>}
                {severityCounts.major > 0 && <span className="severity-tag major">{severityCounts.major} maj</span>}
                {severityCounts.minor > 0 && <span className="severity-tag minor">{severityCounts.minor} min</span>}
              </div>
            </div>
          </div>
          <div className="acc-eval-mini-stats">
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Ratio</span>
              <span className="acc-eval-mini-stat-value">{complianceRatio(allViolations.length, totalCompliant)}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Files</span>
              <span className="acc-eval-mini-stat-value">{topFiles.length}</span>
            </div>
            <div className="acc-eval-mini-stat">
              <span className="acc-eval-mini-stat-label">Principles</span>
              <span className="acc-eval-mini-stat-value">{uniquePrinciples}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Remove the old ExplorerStatsGrid function (lines 77-107)**

Delete the entire `ExplorerStatsGrid` function — it's no longer used.

- [ ] **Step 4: Verify `complianceRatio` is imported**

Check that `complianceRatio` is already imported in ExplorerPage.jsx. If not, add it to the existing formatters import:

```jsx
import { scoreColorClass, complianceRatio } from '../../../utils/formatters.js';
```

- [ ] **Step 5: Verify the Explorer page renders**

Navigate to the Explorer page and open a dimension. The compact panel should show the smaller circle with inline severity tags and the mini-stats row.

- [ ] **Step 6: Commit**

```bash
git add src/quodeq/ui/src/features/explorer/components/ExplorerPage.jsx
git commit -m "feat(ui): rewrite ExplorerPage DimensionOverview with golden-split compact layout"
```

---

### Task 6: Clean up unused CSS and verify all panels

**Files:**
- Modify: `src/quodeq/ui/src/styles/dashboard.css`

- [ ] **Step 1: Search for any remaining references to removed classes**

Search the codebase for `.acc-eval-hero`, `.acc-eval-grade-chip`, `.acc-eval-score-row`, `.acc-eval-score`, `.acc-eval-score-denom`. If any references remain outside of CSS, update them.

Run: `grep -r "acc-eval-hero\|acc-eval-grade-chip\|acc-eval-score-row\|acc-eval-score-denom\|acc-eval-score[^-]" src/quodeq/ui/src/ --include="*.jsx" --include="*.js"`

Expected: no matches (all references should have been updated in Tasks 3-4).

- [ ] **Step 2: Search for any references to RunOverviewPanel using the old classes**

The file `RunOverviewPanel.jsx` was listed as having `acc-eval-panel` references. Check if it uses any of the removed classes.

Run: `grep -n "acc-eval" src/quodeq/ui/src/features/dashboard/components/RunOverviewPanel.jsx`

If it uses removed classes, update it to match the new pattern.

- [ ] **Step 3: Full build check**

Run: `cd src/quodeq/ui && npx vite build 2>&1 | tail -5`
Expected: build succeeds with no errors

- [ ] **Step 4: Visual verification**

Open the app and verify:
1. Dashboard accumulated panel: golden-split, circle with score+grade, two stats (violations + ratio)
2. Dashboard single-run panel: golden-split, circle with score+grade, violations + ratio + mini-stats (files, principles, dimensions)
3. Explorer dimension panel: compact golden-split, smaller circle, inline severity tags, mini-stats row
4. Responsive: resize to <480px, panels should stack vertically

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "fix(ui): clean up unused acc-eval CSS classes after panel redesign"
```
