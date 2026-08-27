import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  putStandardsVisibility: vi.fn(),
}));
vi.mock('../../../api/shared.js', () => ({
  sharedListProjects: vi.fn(),
  sharedGetCompareSummary: vi.fn(),
}));

import { getCompareSummary, getDimensionEval } from '../../../api/index.js';
import { sharedListProjects, sharedGetCompareSummary } from '../../../api/shared.js';

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
  // Default: no shared repository configured — the local-only flow.
  sharedListProjects.mockRejectedValue(Object.assign(new Error('no shared repository configured'), { status: 409 }));
  sharedGetCompareSummary.mockRejectedValue(new Error('unexpected shared fetch'));
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

  it('renders a table skeleton (not a bare text line) before projects load', () => {
    const { container } = renderPage({ projectsLoaded: false });
    expect(container.querySelector('.compare-skeleton')).toBeTruthy();
    expect(container.querySelector('.compare-loading')).toBeNull();
  });

  it('renders a row per project once summaries arrive', async () => {
    renderPage();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(await screen.findByText('beta')).toBeInTheDocument();
    expect((await screen.findAllByText('7.4')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('5.9')).length).toBeGreaterThan(0);
  });

  it('a row name opens the project', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    // Scope to the table: project names also appear in the attention strip.
    const name = (await screen.findAllByText('alpha'))
      .find((el) => el.classList.contains('compare-row__name'));
    await userEvent.click(name);
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('alpha', 'local'));
  });

  it('rows carry the trend spark and severity split inline; the expansion is gone', async () => {
    const { container } = renderPage();
    await screen.findByText('alpha');
    // One spark per scored row (both fixtures have a 2-point trend).
    await waitFor(() => expect(
      container.querySelectorAll('.compare-row .compare-trendline'),
    ).toHaveLength(2));
    // Severity split as colored counts (each fixture row carries 1 critical).
    expect(screen.getAllByText('1 crit').length).toBeGreaterThan(1);
    expect(container.querySelector('.compare-rowdetail')).toBeNull();
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

  it('a matrix cell opens that project’s own dimension page, not the compare drill-down', async () => {
    const onOpenProjectDimension = vi.fn();
    renderPage({ onOpenProjectDimension });
    await screen.findByText('alpha');
    const matrix = await screen.findByLabelText('Score matrix');
    await userEvent.click(within(matrix).getByTitle('open security in alpha'));
    expect(onOpenProjectDimension).toHaveBeenCalledWith({
      id: 'alpha', source: 'local', runId: 'r2', dimName: 'Security', dateLabel: '25 Aug',
    });
    expect(screen.queryByText(/PROJECT_STANDINGS/)).toBeNull();
  });

  it('score matrix grids every project; column headers rank by that column', async () => {
    renderPage();
    await screen.findByText('alpha');
    const matrix = await screen.findByLabelText('Score matrix');
    // Both projects' Security scores appear as cells (7.0 and 5.5).
    expect(within(matrix).getByText('7.0')).toBeInTheDocument();
    expect(within(matrix).getByText('5.5')).toBeInTheDocument();
    const rowOrder = () => within(matrix).getAllByRole('row')
      .map((r) => r.textContent)
      .filter((tx) => /alpha|beta/.test(tx));
    // Default order is the table's (score desc): alpha first.
    expect(rowOrder()[0]).toMatch(/alpha/);
    // First click ranks best-first (alpha still first), second flips it.
    const colBtn = within(matrix).getByRole('button', { name: /Rank by security/ });
    await userEvent.click(colBtn);
    expect(rowOrder()[0]).toMatch(/alpha/);
    await userEvent.click(within(matrix).getByRole('button', { name: /Rank by security/ }));
    expect(rowOrder()[0]).toMatch(/beta/);
  });

  it('the dimension drill-down carries the principle matrix', async () => {
    renderPage();
    await screen.findByText('alpha');
    const dimButtons = await screen.findAllByText('security');
    await userEvent.click(dimButtons[dimButtons.length - 1]);
    expect(await screen.findByText(/PROJECT_STANDINGS/)).toBeInTheDocument();
    expect(screen.getByText(/PRINCIPLE_MATRIX/)).toBeInTheDocument();
  });

  it('drills into a dimension', async () => {
    renderPage();
    await screen.findByText('alpha');
    const dimButtons = await screen.findAllByText('security');
    await userEvent.click(dimButtons[dimButtons.length - 1]);
    expect(await screen.findByText(/PROJECT_STANDINGS/)).toBeInTheDocument();
    expect(screen.getByText('leads the scope')).toBeInTheDocument();
    expect(screen.getByText('trails the scope')).toBeInTheDocument();
    // No local back button: the app breadcrumb owns the way back.
    expect(screen.queryByText(/ALL DIMENSIONS/)).toBeNull();
  });

  it('the header launcher duels an exactly-two scope directly, no popover', async () => {
    renderPage();
    await screen.findByText('alpha');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    expect(await screen.findByText(/PRINCIPLE_DIFFS/)).toBeInTheDocument();
    // Left minus right: +1.5 shows as the overall gap card and again on the
    // security dimension and principle rows (7.0 vs 5.5).
    expect(screen.getAllByText('+1.5').length).toBeGreaterThan(1);
    expect(screen.getByText('alpha leads by 1.5')).toBeInTheDocument();
  });

  it('the header launcher runs the two-pick flow on larger scopes', async () => {
    renderPage({
      projects: PROJECTS.concat([{
        id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { py: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(1),
      }]),
    });
    await screen.findByText('gamma');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    // First pick pins side A and stays open; second pick navigates.
    await userEvent.click(await screen.findByRole('menuitem', { name: /alpha/ }));
    expect(screen.getByLabelText('Clear the first pick')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('menuitem', { name: /beta/ }));
    expect(await screen.findByText(/PRINCIPLE_DIFFS/)).toBeInTheDocument();
  });

  it('hides dimensions the user has disabled, like the Overview', async () => {
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
    // Same browser-local set the Overview filters by (and the Standards
    // screen's stars write) — the whole point of the shared source of truth.
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['security']));
    renderPage();
    await screen.findByText('alpha');
    expect(await screen.findAllByText('security')).not.toHaveLength(0);
    expect(screen.queryByText('usability')).toBeNull();
  });

  it('closes the scope picker on outside click and on Escape', async () => {
    renderPage();
    await screen.findByText('alpha');
    const toggle = screen.getByText(/all 2 projects/);
    await userEvent.click(toggle);
    expect(screen.getByText('Projects in scope')).toBeInTheDocument();
    // Click anywhere outside the picker.
    await userEvent.click(screen.getByText(/PROJECTS ·/));
    expect(screen.queryByText('Projects in scope')).toBeNull();
    // Escape closes it too.
    await userEvent.click(toggle);
    expect(screen.getByText('Projects in scope')).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(screen.queryByText('Projects in scope')).toBeNull();
  });

  it('standings rows open that project view of the same dimension', async () => {
    const onOpenProjectDimension = vi.fn();
    const onOpenProject = vi.fn();
    renderPage({ onOpenProjectDimension, onOpenProject });
    await screen.findByText('alpha');
    await userEvent.click((await (async () => { const b = await screen.findAllByText('security'); return b[b.length - 1]; })()));
    await userEvent.click(await screen.findByText('leads the scope'));
    expect(onOpenProjectDimension).toHaveBeenCalledWith(
      expect.objectContaining({ runId: 'r2', dimName: 'Security' }),
    );
    expect(onOpenProject).not.toHaveBeenCalled();
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
    await userEvent.click((await (async () => { const b = await screen.findAllByText('security'); return b[b.length - 1]; })()));
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

describe('ComparePage remote projects', () => {
  const REMOTE = {
    id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { rb: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(3),
  };

  beforeEach(() => {
    sharedListProjects.mockResolvedValue({ projects: [REMOTE], lastSynced: null, stale: false });
    sharedGetCompareSummary.mockResolvedValue(summary(6.5, 6.2));
  });

  it('remote rows join the fleet through the shared route, tagged', async () => {
    renderPage();
    expect(await screen.findByText('gamma')).toBeInTheDocument();
    expect((await screen.findAllByText('remote')).length).toBeGreaterThan(0);
    await waitFor(() => expect(sharedGetCompareSummary).toHaveBeenCalledWith('gamma'));
    // The local endpoint is never asked for the remote project.
    expect(getCompareSummary).not.toHaveBeenCalledWith('gamma');
  });

  it('opening a remote row switches to the shared source', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    const rowName = (await screen.findAllByText('gamma'))
      .find((el) => el.classList.contains('compare-row__name'));
    await userEvent.click(rowName);
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('gamma', 'shared'));
  });

  it('duels a local project against a remote one', async () => {
    renderPage();
    await screen.findByText('gamma');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /alpha/ }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /gamma/ }));
    expect(await screen.findByText(/PRINCIPLE_DIFFS/)).toBeInTheDocument();
  });

  it('a published copy of a local project is deduplicated, local prevailing', async () => {
    // Same id as the local 'alpha' — the Projects page's merge rule says
    // this is the SAME project, so no remote row appears for it.
    sharedListProjects.mockResolvedValue({
      projects: [
        { id: 'alpha', name: 'alpha', displayName: 'alpha', languageStats: { py: 100 }, runsCount: 2, latestDate: iso(5) },
        REMOTE,
      ],
      lastSynced: null,
      stale: false,
    });
    renderPage();
    await screen.findByText('gamma');
    const alphaRows = screen.getAllByText('alpha')
      .filter((el) => el.classList.contains('compare-row__name'));
    expect(alphaRows).toHaveLength(1);
    // The local endpoint serves alpha; the shared route is only asked for
    // the genuinely remote project.
    await waitFor(() => expect(getCompareSummary).toHaveBeenCalledWith('alpha'));
    expect(sharedGetCompareSummary).not.toHaveBeenCalledWith('alpha');
  });

  it('leaves the fleet local-only when no shared repository is configured', async () => {
    sharedListProjects.mockRejectedValue(Object.assign(new Error('no shared repository configured'), { status: 409 }));
    renderPage();
    expect(await screen.findByText('alpha')).toBeInTheDocument();
    expect(screen.queryByText('gamma')).toBeNull();
    expect(screen.queryByText('remote')).toBeNull();
  });
});
