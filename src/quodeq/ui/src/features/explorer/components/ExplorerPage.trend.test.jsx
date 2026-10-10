import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

const data = vi.hoisted(() => ({ d: null }));
const statsProps = vi.hoisted(() => ({ last: null }));

// The page's own-trend query needs a QueryClient; these render it bare.
vi.mock('./useExplorerTrend.js', () => ({ useExplorerTrend: (_p, _s, trend) => trend ?? [] }));
vi.mock('./explorerDataHooks.js', () => ({
  useExplorerData: () => data.d,
  buildEvalPrincipalFn: () => () => ({}),
}));
vi.mock('../hooks/useStandardDescriptions.js', () => ({ useStandardDescriptions: () => ({ standardDescription: '' }) }));
vi.mock('./useExplorerPageSpecs.jsx', () => ({ useExplorerPageSpecs: () => {} }));
vi.mock('./ExplorerStatsPanel.jsx', () => ({ default: (props) => { statsProps.last = props; return null; } }));
vi.mock('./ExplorerRadialPanel.jsx', () => ({ default: () => null }));
vi.mock('./PrinciplesCardsRow.jsx', () => ({ default: () => null }));
vi.mock('../../dashboard/components/TopOffendingFilesTable.jsx', () => ({ default: () => null }));

import ExplorerPage from './ExplorerPage.jsx';

// The dimension page's arrows follow the chart's grouping the way the
// Overview's do: the title and the score carry the dimension's change
// since the previous period, the chips their count changes.
const row = (runId, dateISO, score, critical, majors) => ({
  runId, dateISO, dateLabel: dateISO.slice(0, 10), status: 'completed',
  dimensionDetails: [{ dimension: 'security', score, critical, majors }],
});
const TREND = [
  row('r3', '2026-03-24T10:00:00', 7.5, 2, 5),
  row('r2', '2026-03-18T10:00:00', 7.0, 3, 9),
];

describe('ExplorerPage trend arrows', () => {
  beforeEach(() => {
    statsProps.last = null;
    data.d = {
      loading: false, error: null, waiting: false, isFetching: false,
      evalData: { dimension: 'security', principleGrades: [] },
      overallGrade: { score: '7.5' },
      principleGrades: [{ principle: 'P1', score: '7.5', grade: 'B' }],
      allViolations: [],
      complianceByPrinciple: new Map([['P1', [{ file: 'a.py' }]]]),
      topFiles: [], severityCounts: {}, totalCompliant: 1,
    };
  });

  it('puts the period delta on the title and hands the score and chip deltas to the stats panel', () => {
    const { container } = render(<ExplorerPage project="demo" dimension="security" granularity="day" trend={TREND} />);
    expect(container.querySelector('.term-header .trend-badge')).toHaveTextContent('+0.5');
    expect(statsProps.last.scoreDelta).toBe(0.5);
    expect(statsProps.last.deltas).toEqual({ critical: -1, major: -3 });
  });

  it('shows no arrow without a previous period', () => {
    const { container } = render(<ExplorerPage project="demo" dimension="security" granularity="day" trend={TREND.slice(0, 1)} />);
    expect(container.querySelector('.term-header .trend-badge')).toBeNull();
    expect(statsProps.last.scoreDelta).toBeNull();
    expect(statsProps.last.deltas).toBeNull();
  });
});
