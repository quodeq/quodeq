import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import ComparePage from './ComparePage.jsx';

vi.mock('../../../api/index.js', () => ({
  getCompareSummary: vi.fn(),
}));

import { getCompareSummary } from '../../../api/index.js';

const iso = (daysAgo) => new Date(Date.now() - daysAgo * 86400000).toISOString();

const PROJECTS = [
  { id: 'alpha', name: 'alpha', displayName: 'alpha', languageStats: { py: 100 }, totalFiles: 200, analyzedFiles: 190, runsCount: 2, latestDate: iso(1) },
  { id: 'beta', name: 'beta', displayName: 'beta', languageStats: { ts: 80 }, totalFiles: 100, analyzedFiles: 100, runsCount: 1, latestDate: iso(2) },
];

function summary(score, dimScore) {
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

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getCompareSummary.mockImplementation((id) => Promise.resolve(
    id === 'alpha' ? summary(7.4, 7.0) : summary(5.9, 5.5),
  ));
});

function renderPage(props = {}) {
  return render(
    <ComparePage
      projects={PROJECTS}
      projectsLoaded
      onOpenProject={vi.fn()}
      {...props}
    />,
    { wrapper: withQueryClient() },
  );
}

describe('ComparePage', () => {
  it('shows the empty state when there are no projects', () => {
    renderPage({ projects: [] });
    expect(screen.getByText('Nothing to compare yet')).toBeInTheDocument();
  });

  it('renders a row per project once summaries arrive', async () => {
    renderPage();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(await screen.findByText('beta')).toBeInTheDocument();
    expect(await screen.findByText('7.4')).toBeInTheDocument();
    expect(await screen.findByText('5.9')).toBeInTheDocument();
  });

  it('opens a project overview on row click', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    const name = await screen.findByText('alpha');
    await userEvent.click(name);
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('alpha'));
  });

  it('drills into a dimension and back', async () => {
    renderPage();
    await screen.findByText('alpha');
    const dimButtons = await screen.findAllByText('security');
    await userEvent.click(dimButtons[0]);
    expect(await screen.findByText(/PROJECT_STANDINGS/)).toBeInTheDocument();
    expect(screen.getByText('leads the scope')).toBeInTheDocument();
    expect(screen.getByText('trails the scope')).toBeInTheDocument();
    await userEvent.click(screen.getByText(/ALL DIMENSIONS/));
    expect(await screen.findByText(/PROJECTS ·/)).toBeInTheDocument();
  });

  it('marks projects whose summary failed', async () => {
    getCompareSummary.mockImplementation((id) => (
      id === 'beta'
        ? Promise.reject(new Error('boom'))
        : Promise.resolve(summary(7.4, 7.0))
    ));
    renderPage();
    expect(await screen.findByText('failed to load scores', undefined, { timeout: 4000 })).toBeInTheDocument();
    // The healthy project still renders its data (row + scope card).
    expect((await screen.findAllByText('7.4')).length).toBeGreaterThan(0);
  });
});
