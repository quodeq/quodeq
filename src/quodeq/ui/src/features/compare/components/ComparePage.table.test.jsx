import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../api/index.js', () => ({
  getFleetCompare: vi.fn(),
  getDimensionEval: vi.fn(),
  sharedGetFleetCompare: vi.fn(),
}));
vi.mock('../../../api/standards.js', () => ({
  getStandardsVisibility: vi.fn(),
  putStandardsVisibility: vi.fn(),
}));
vi.mock('../../../api/shared.js', () => ({
  sharedListProjects: vi.fn(),
}));

import { getDimensionEval, getFleetCompare, sharedGetFleetCompare } from '../../../api/index.js';
import { sharedListProjects } from '../../../api/shared.js';
import { PROJECTS, fleetOf, summary, renderPage, iso, findTableName } from './_comparePage.fixtures.jsx';

/**
 * Split from ComparePage.test.jsx: the local-fleet table, matrix, and
 * drill-down/duel interactions. The remote-projects describe block is
 * split further into ComparePage.remote.test.jsx.
 */

/**
 * Drill into the security dimension. Several nodes render the text
 * "security"; the last one is the fleet table's dimension cell, which is the
 * one that navigates.
 */
async function drillIntoSecurity() {
  const matches = await screen.findAllByText('security');
  await userEvent.click(matches[matches.length - 1]);
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  getFleetCompare.mockImplementation(fleetOf((id) => (
    id === 'alpha' ? summary(7.4, 7.0) : summary(5.9, 5.5)
  )));
  // Default: no shared repository configured — the local-only flow.
  sharedListProjects.mockRejectedValue(Object.assign(new Error('no shared repository configured'), { status: 409 }));
  sharedGetFleetCompare.mockRejectedValue(new Error('unexpected shared fetch'));
});

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
    expect(await findTableName('alpha')).toBeInTheDocument();
    expect(await findTableName('beta')).toBeInTheDocument();
    expect((await screen.findAllByText('7.4')).length).toBeGreaterThan(0);
    expect((await screen.findAllByText('5.9')).length).toBeGreaterThan(0);
  });

  it('a row name opens the project', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    // Scope to the table: project names also appear in the matrix, the map and the attention list.
    const name = await findTableName('alpha');
    await userEvent.click(name);
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('alpha', 'local'));
  });

  it('rows carry size and exposure per size, not raw counts', async () => {
    const { container } = renderPage();
    await findTableName('alpha');
    const rows = container.querySelectorAll('.compare-fleettable__row:not(.compare-fleettable__row--head)');
    expect(rows).toHaveLength(2);
    // Columns: files, violations per 100 files, critical per 1,000 files.
    const head = container.querySelector('.compare-fleettable__row--head');
    for (const col of ['files', 'viol / 100', 'crit / 1k', 'last scan']) expect(head).toHaveTextContent(col);
  });

  it('a column header ranks the projects, and again reverses', async () => {
    const { container } = renderPage();
    await findTableName('alpha');
    const order = () => [...container.querySelectorAll('.compare-fleettable__namebtn')].map((b) => b.textContent);
    expect(order()).toEqual(['alpha', 'beta']);
    const table = screen.getByRole('region', { name: 'Projects ranked' });
    await userEvent.click(within(table).getByRole('button', { name: 'Rank by score' }));
    expect(order()).toEqual(['beta', 'alpha']);
  });

  it('collapses never-evaluated projects into a single line', async () => {
    getFleetCompare.mockImplementation(fleetOf((id) => (id === 'alpha'
      ? summary(7.4, 7.0)
      : { summary: {}, dimensions: [], trend: [], runsCount: 0, lastRun: null })));
    const { container } = renderPage();
    await findTableName('alpha');
    // Once beta settles with no data it leaves the ranked rows for the
    // collapsed line (it may briefly render as a pending row before that).
    expect(await screen.findByText(/1 projects without evaluations/)).toBeInTheDocument();
    await waitFor(() => expect([...container.querySelectorAll('.compare-fleettable__namebtn')].map((b) => b.textContent)).toEqual(['alpha']));
  });

  it('a matrix cell opens that project’s own dimension page, not the compare drill-down', async () => {
    const onOpenProjectDimension = vi.fn();
    renderPage({ onOpenProjectDimension });
    await findTableName('alpha');
    const matrix = await screen.findByLabelText('Score matrix');
    await userEvent.click(within(matrix).getByTitle('open security in alpha'));
    expect(onOpenProjectDimension).toHaveBeenCalledWith({
      id: 'alpha', source: 'local', runId: 'r2', dimName: 'Security', dateLabel: '25 Aug',
    });
    expect(screen.queryByText(/PROJECT_STANDINGS/)).toBeNull();
  });

  it('score matrix grids every project; column headers rank by that column', async () => {
    renderPage();
    await findTableName('alpha');
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
    await findTableName('alpha');
    const dimButtons = await screen.findAllByText('security');
    await userEvent.click(dimButtons[dimButtons.length - 1]);
    expect(await screen.findByText(/PROJECT_STANDINGS/)).toBeInTheDocument();
    expect(screen.getByText(/PRINCIPLE_MATRIX/)).toBeInTheDocument();
  });

  it('the header dimension button lists the board and opens the pick', async () => {
    renderPage();
    await findTableName('alpha');
    await userEvent.click(await screen.findByRole('button', { name: 'Open a dimension drill-down' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /security/ }));
    expect(await screen.findByText(/PROJECT_STANDINGS/)).toBeInTheDocument();
  });

  it('drills into a dimension', async () => {
    renderPage();
    await findTableName('alpha');
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
    await findTableName('alpha');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    expect(await screen.findByText(/GAP_SOURCES/)).toBeInTheDocument();
    // Left minus right: +1.5 shows in the verdict and again as security's
    // share of the gap (the only dimension, so all of it: 7.0 vs 5.5).
    expect(screen.getAllByText('+1.5').length).toBeGreaterThan(1);
    const verdict = screen.getByRole('group', { name: 'Head-to-head comparison' });
    expect(verdict).toHaveTextContent(/alpha leads beta by \+1\.5/);
  });

  it('the header launcher runs the two-pick flow on larger scopes', async () => {
    renderPage({
      projects: PROJECTS.concat([{
        id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { py: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(1),
      }]),
    });
    await findTableName('gamma');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    // First pick pins side A and stays open; second pick navigates.
    await userEvent.click(await screen.findByRole('menuitem', { name: /alpha/ }));
    expect(screen.getByLabelText('Clear the first pick')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('menuitem', { name: /beta/ }));
    expect(await screen.findByText(/GAP_SOURCES/)).toBeInTheDocument();
  });

  it('hides dimensions the user has disabled, like the Overview', async () => {
    getFleetCompare.mockImplementation(fleetOf(() => ({
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
    })));
    // Same browser-local set the Overview filters by (and the Standards
    // screen's stars write) — the whole point of the shared source of truth.
    localStorage.setItem('quodeq-visible-standards', JSON.stringify(['security']));
    renderPage();
    await findTableName('alpha');
    expect(await screen.findAllByText('security')).not.toHaveLength(0);
    expect(screen.queryByText('usability')).toBeNull();
  });

  it('closes the scope picker on outside click and on Escape', async () => {
    renderPage();
    await findTableName('alpha');
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
    await findTableName('alpha');
    await drillIntoSecurity();
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
    await findTableName('alpha');
    await drillIntoSecurity();
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
    getFleetCompare.mockImplementation(fleetOf((id) => {
      if (id === 'beta') throw new Error('boom');
      return summary(7.4, 7.0);
    }));
    renderPage();
    expect(await screen.findByText('failed to load scores', undefined, { timeout: 4000 })).toBeInTheDocument();
    // The healthy project still renders its data (row + scope card).
    expect((await screen.findAllByText('7.4')).length).toBeGreaterThan(0);
  });
});
