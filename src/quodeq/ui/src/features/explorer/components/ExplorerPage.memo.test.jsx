import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

const calls = vi.hoisted(() => ({ radial: 0, enriched: 0, rootFile: 0 }));
const data = vi.hoisted(() => ({ d: null }));

vi.mock('./explorerDataHooks.js', () => ({
  useExplorerData: () => data.d,
  buildEvalPrincipalFn: () => () => ({}),
}));
vi.mock('./explorerPrincipleView.js', async (importOriginal) => {
  const m = await importOriginal();
  return {
    ...m,
    buildRadialPrinciples: (...a) => { calls.radial += 1; return m.buildRadialPrinciples(...a); },
    buildEnrichedPrinciples: (...a) => { calls.enriched += 1; return m.buildEnrichedPrinciples(...a); },
  };
});
vi.mock('../../../utils/explorerUtils.js', async (importOriginal) => {
  const m = await importOriginal();
  return { ...m, buildProjectRootFile: (...a) => { calls.rootFile += 1; return m.buildProjectRootFile(...a); } };
});
vi.mock('../hooks/useStandardDescriptions.js', () => ({ useStandardDescriptions: () => ({ standardDescription: '' }) }));
vi.mock('./useExplorerPageSpecs.jsx', () => ({ useExplorerPageSpecs: () => {} }));
vi.mock('./ExplorerStatsPanel.jsx', () => ({ default: () => null }));
vi.mock('./ExplorerRadialPanel.jsx', () => ({ default: () => null }));
vi.mock('./PrinciplesCardsRow.jsx', () => ({ default: () => null }));
vi.mock('../../dashboard/components/TopOffendingFilesTable.jsx', () => ({ default: () => null }));

import ExplorerPage from './ExplorerPage.jsx';

describe('ExplorerPage memoization', () => {
  beforeEach(() => {
    calls.radial = 0; calls.enriched = 0; calls.rootFile = 0;
    data.d = {
      loading: false, error: null, waiting: false, isFetching: false,
      evalData: { dimension: 'security', principleGrades: [] },
      overallGrade: { score: '7.0' },
      principleGrades: [{ principle: 'P1', score: '7.0', grade: 'B' }],
      allViolations: [],
      complianceByPrinciple: new Map([['P1', [{ file: 'a.py' }]]]),
      topFiles: [], severityCounts: {}, totalCompliant: 1,
    };
  });

  it('does not rebuild the dimension file or principle views on an unrelated re-render', () => {
    const { rerender } = render(<ExplorerPage project="demo" dimension="security" granularity="day" />);
    expect(calls).toEqual({ radial: 1, enriched: 1, rootFile: 1 });
    rerender(<ExplorerPage project="demo" dimension="security" granularity="week" />);
    expect(calls).toEqual({ radial: 1, enriched: 1, rootFile: 1 });
  });
});
