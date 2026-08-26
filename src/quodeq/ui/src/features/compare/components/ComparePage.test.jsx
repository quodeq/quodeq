import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import ComparePage from './ComparePage.jsx';

vi.mock('../../../api/index.js', () => ({
  getCompareSummary: vi.fn(),
  getDimensionEval: vi.fn(),
}));
vi.mock('../../../api/standards.js', () => ({
  getStandardsVisibility: vi.fn(),
}));

import { getCompareSummary, getDimensionEval } from '../../../api/index.js';
import { getStandardsVisibility } from '../../../api/standards.js';

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

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getCompareSummary.mockImplementation((id) => Promise.resolve(
    id === 'alpha' ? summary(7.4, 7.0) : summary(5.9, 5.5),
  ));
  // Null ids = no filtering (fail-open), so most tests see the raw payload.
  getStandardsVisibility.mockResolvedValue({ visibleStandardIds: null, isDefault: true });
});

/* Mimics the App wiring: `dimension` is a route param — drilling in pushes,
   switching replaces, back pops. The harness keeps a tiny stack so the
   push/pop contract is exercised, not just a boolean. */
function NavHarness(props) {
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

function renderPage(props = {}) {
  return render(<NavHarness {...props} />, { wrapper: withQueryClient() });
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

  it('expands a row on click; the expansion opens the project overview', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    const name = await screen.findByText('alpha');
    await userEvent.click(name);
    // Row click expands the detail (severity, dimensions, actions) instead
    // of navigating away.
    expect(onOpenProject).not.toHaveBeenCalled();
    await userEvent.click(await screen.findByText(/open project/));
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('alpha'));
  });

  it('keeps multiple rows expanded independently', async () => {
    renderPage();
    // Scope to table rows: project names also appear in the attention strip.
    const rowName = (name) => screen.getAllByText(name)
      .find((el) => el.classList.contains('compare-row__name'));
    await screen.findByText('alpha');
    await userEvent.click(rowName('alpha'));
    await userEvent.click(rowName('beta'));
    // Both detail blocks stay open side by side.
    expect(await screen.findAllByText(/open project/)).toHaveLength(2);
    // Toggling one closed leaves the other open.
    await userEvent.click(rowName('alpha'));
    expect(await screen.findAllByText(/open project/)).toHaveLength(1);
  });

  it('collapses never-evaluated projects into a single line', async () => {
    getCompareSummary.mockImplementation((id) => (id === 'alpha'
      ? Promise.resolve(summary(7.4, 7.0))
      : Promise.resolve({
        summary: {}, dimensions: [], trend: [], runsCount: 0, lastRun: null,
      })));
    renderPage();
    await screen.findByText('alpha');
    // Once beta settles with no data it leaves the table for the collapsed
    // line (it may briefly render as a pending row before that).
    const toggle = await screen.findByText(/1 projects without evaluations/);
    expect(screen.queryByText('beta')).toBeNull();
    await userEvent.click(toggle);
    expect(await screen.findByText('beta')).toBeInTheDocument();
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

  it('opens the head-to-head duel when the scope is exactly two projects', async () => {
    renderPage();
    await screen.findByText('alpha');
    // Two projects in the fleet = effective scope of two, so the action shows.
    const cta = await screen.findByText('compare these two');
    await userEvent.click(cta);
    expect(await screen.findByText(/PRINCIPLE_DIFFS/)).toBeInTheDocument();
    // Left minus right: +1.5 shows as the overall gap card and again on the
    // security dimension and principle rows (7.0 vs 5.5).
    expect(screen.getAllByText('+1.5').length).toBeGreaterThan(1);
    expect(screen.getByText('alpha leads by 1.5')).toBeInTheDocument();
    await userEvent.click(screen.getByText(/ALL PROJECTS/));
    expect(await screen.findByText(/PROJECTS ·/)).toBeInTheDocument();
  });

  it('hides the duel action when more than two projects are in scope', async () => {
    renderPage({
      projects: PROJECTS.concat([{
        id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { py: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(1),
      }]),
    });
    await screen.findByText('gamma');
    expect(screen.queryByText('compare these two')).not.toBeInTheDocument();
  });

  it('hides dimensions a project has disabled, like the Overview', async () => {
    getCompareSummary.mockImplementation(() => Promise.resolve({
      ...summary(7.0, 7.0),
      dimensions: [
        ...summary(7.0, 7.0).dimensions,
        {
          dimension: 'Usability',
          overallScore: '8.0/10',
          totals: { violationCount: 2, severity: { critical: 0, major: 1, minor: 1 } },
          principles: [],
        },
      ],
    }));
    getStandardsVisibility.mockResolvedValue({ visibleStandardIds: ['security'], isDefault: false });
    renderPage();
    await screen.findByText('alpha');
    expect(await screen.findAllByText('security')).not.toHaveLength(0);
    expect(screen.queryByText('usability')).toBeNull();
  });

  it('opens a project-specific principle from a principle card', async () => {
    getDimensionEval.mockResolvedValue({
      dimension: 'Security',
      principles: [{ name: 'Integrity', violations: [], compliance: [] }],
      principleGrades: [{ principle: 'Integrity', score: '7.0', grade: 'Good' }],
      violations: [],
      compliance: [],
    });
    const onOpenEvalPrincipal = vi.fn();
    renderPage({ onOpenEvalPrincipal });
    await screen.findByText('alpha');
    await userEvent.click((await screen.findAllByText('security'))[0]);
    // beta leads security (5.5 vs... alpha 7.0 leads actually) — click the
    // integrity lead entry, whoever it is, via its accessible title.
    const leads = await screen.findAllByTitle(/open integrity in/);
    await userEvent.click(leads[0]);
    await waitFor(() => expect(onOpenEvalPrincipal).toHaveBeenCalled());
    const evalPrincipal = onOpenEvalPrincipal.mock.calls[0][0];
    expect(evalPrincipal.principle).toBe('Integrity');
    expect(evalPrincipal.runId).toBe('r2');
    expect(['alpha', 'beta']).toContain(evalPrincipal.project);
    expect(getDimensionEval).toHaveBeenCalledWith(evalPrincipal.project, 'r2', 'Security');
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
