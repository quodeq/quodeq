import { vi } from 'vitest';
import { render } from '@testing-library/react';
import { useState } from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import ComparePage from './ComparePage.jsx';

/**
 * Shared fixtures for ComparePage.*.test.jsx siblings.
 *
 * Split out of ComparePage.test.jsx. Does not itself declare any
 * vi.mock(...) calls (those are file-scoped/hoisted) — each test file
 * that uses these helpers must declare its own mocks for
 * ../../../api/index.js, ../../../api/standards.js, and
 * ../../../api/shared.js first.
 */

export const iso = (daysAgo) => new Date(Date.now() - daysAgo * 86400000).toISOString();

export const PROJECTS = [
  { id: 'alpha', name: 'alpha', displayName: 'alpha', languageStats: { py: 100 }, totalFiles: 200, analyzedFiles: 190, runsCount: 2, latestDate: iso(1) },
  { id: 'beta', name: 'beta', displayName: 'beta', languageStats: { ts: 80 }, totalFiles: 100, analyzedFiles: 100, runsCount: 1, latestDate: iso(2) },
];

export function summary(score, dimScore) {
  return {
    summary: {
      numericAverage: score,
      overallGrade: 'Good',
      totalViolations: 12,
      totalCompliance: 88,
      severity: { critical: 1, major: 4, minor: 7 },
    },
    dimensions: [{
      dimension: 'Security',
      overallScore: `${dimScore}/10`,
      overallGrade: 'Good',
      fromRunId: 'r2',
      fromDateLabel: '25 Aug',
      totals: { violationCount: 6, severity: { critical: 1, major: 2, minor: 3 } },
      principles: [
        { principle: 'Integrity', score: `${dimScore}` },
        { principle: 'Confidentiality', score: `${dimScore}` },
        { principle: 'Authenticity', score: `${dimScore}` },
      ],
    }],
    trend: [
      { runId: 'r1', dateISO: iso(10), numericAverage: score - 0.4, dimensionDetails: [{ dimension: 'Security', score: dimScore - 0.4 }] },
      { runId: 'r2', dateISO: iso(1), numericAverage: score, dimensionDetails: [{ dimension: 'Security', score: dimScore }] },
    ],
    runsCount: 2,
    lastRun: { runId: 'r2', dateISO: iso(1), status: 'complete' },
  };
}

/* Mimics the App wiring: `dimension` is a route param — drilling in pushes,
   switching replaces, back pops. The harness keeps a tiny stack so the
   push/pop contract is exercised, not just a boolean. */
export function NavHarness(props) {
  const [stack, setStack] = useState([{}]);
  const params = stack[stack.length - 1];
  return (
    <ComparePage
      projects={PROJECTS}
      projectsLoaded
      onOpenProject={vi.fn()}
      dimension={params.dimension || null}
      duel={params.duel || null}
      onOpenDimension={(key) => setStack((s) => s.concat([{ dimension: key }]))}
      onSwitchDimension={(key) => setStack((s) => s.slice(0, -1).concat([{ dimension: key }]))}
      onOpenDuel={(ids) => setStack((s) => s.concat([{ duel: ids }]))}
      onBack={() => setStack((s) => (s.length > 1 ? s.slice(0, -1) : s))}
      {...props}
    />
  );
}

export function renderPage(props = {}) {
  return render(<NavHarness {...props} />, { wrapper: withQueryClient() });
}
