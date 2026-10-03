import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import AccumulatedOverviewPanel from './AccumulatedOverviewPanel.jsx';
import { SidePaneProvider } from '../../side-pane/SidePaneProvider.jsx';

const TREND = [
  { runId: 't1', dateISO: '2026-07-03T10:00:00', dateLabel: 'Jul 3', numericAverage: 9, overallGrade: 'A', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 9 }] },
  { runId: 't2', dateISO: '2026-06-15T10:00:00', dateLabel: 'Jun 15', numericAverage: 7, overallGrade: 'B', dimensions: ['maintainability'], dimensionDetails: [{ dimension: 'maintainability', score: 7 }] },
];
const DIMS = [{ dimension: 'maintainability', overallScore: '7.0/10' }];

function data(extra) {
  return {
    accumulated: { summary: { numericAverage: 7 }, dimensions: DIMS, topFiles: [{ file: 'a.py', count: 3 }] },
    accumulatedDimensions: DIMS,
    availableRuns: [],
    dailyRuns: null,
    overviewRunIndex: 0,
    trend: TREND,
    selectedRunId: 't1',
    granularity: 'day',
    projectInfo: null,
    selectedProject: 'proj1',
    selectedSource: 'local',
    ...extra,
  };
}

const callbacks = { onRunClick: vi.fn(), onDimensionClick: vi.fn(), onNavigate: vi.fn() };

function renderPanel(extra) {
  return render(
    <SidePaneProvider>
      <AccumulatedOverviewPanel data={data(extra)} callbacks={callbacks} />
    </SidePaneProvider>,
  );
}

const MIN_SECTIONS = 3;
const DIM_FLOOR = 0.7;

describe('AccumulatedOverviewPanel pending sections', () => {
  it('marks each section pending while the dashboard is refreshing, never the page', () => {
    const { container } = renderPanel({ refreshing: true });
    const sections = container.querySelectorAll('.section-pending');
    expect(sections.length).toBeGreaterThanOrEqual(MIN_SECTIONS);
    expect(container.querySelector('.acc-eval-panel.section-pending')).not.toBeNull();
    expect(container.querySelector('.history-panels-row.section-pending')).not.toBeNull();
    expect(container.querySelector('.quality-dimensions.section-pending')).not.toBeNull();
    expect(container.querySelector('.dashboard-refreshing')).toBeNull();
    expect(container.querySelector('.quality-dimensions--pending')).toBeNull();
  });

  it('also marks sections pending while the scores query is in flight', () => {
    const { container } = renderPanel({ scoresPending: true });
    expect(container.querySelector('.quality-dimensions.section-pending')).not.toBeNull();
    expect(container.querySelector('.acc-eval-panel.section-pending')).not.toBeNull();
  });

  it('wears no pending class when idle', () => {
    const { container } = renderPanel({});
    expect(container.querySelector('.section-pending')).toBeNull();
  });
});

describe('section-pending stylesheet', () => {
  const css = readFileSync(resolve(dirname(fileURLToPath(import.meta.url)), '../../../styles/dashboard.css'), 'utf8');

  it('has no page-level dim rule left', () => {
    expect(css).not.toMatch(/\.dashboard-refreshing\s*\{/);
    expect(css).not.toMatch(/quality-dimensions--pending/);
  });

  it('does not dim pending content below the readable floor', () => {
    // Only the reduced-motion static line carries an opacity, not the content.
    const rules = css.match(/\.section-pending[^{]*\{[^}]*\}/g);
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) {
      const m = rule.match(/opacity:\s*([\d.]+)/);
      if (m) expect(Number(m[1])).toBeGreaterThanOrEqual(DIM_FLOOR);
    }
  });
});
