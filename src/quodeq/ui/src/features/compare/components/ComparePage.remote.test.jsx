import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
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

import { getFleetCompare, sharedGetFleetCompare } from '../../../api/index.js';
import { sharedListProjects } from '../../../api/shared.js';
import { fleetOf, summary, renderPage, iso, findTableName } from './_comparePage.fixtures.jsx';

/**
 * Split from ComparePage.test.jsx: remote/shared-fleet projects.
 */

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

describe('ComparePage remote projects', () => {
  const REMOTE = {
    id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { rb: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(3),
  };

  beforeEach(() => {
    sharedListProjects.mockResolvedValue({ projects: [REMOTE], lastSynced: null, stale: false });
    sharedGetFleetCompare.mockImplementation(fleetOf(() => summary(6.5, 6.2)));
  });

  it('remote rows join the fleet through the shared route, tagged', async () => {
    renderPage();
    expect(await findTableName('gamma')).toBeInTheDocument();
    expect((await screen.findAllByText('remote')).length).toBeGreaterThan(0);
    await waitFor(() => expect(sharedGetFleetCompare).toHaveBeenCalledWith(['gamma']));
    // The local endpoint is never asked for the remote project.
    expect(getFleetCompare.mock.calls.flat(2)).not.toContain('gamma');
  });

  it('opening a remote row switches to the shared source', async () => {
    const onOpenProject = vi.fn();
    renderPage({ onOpenProject });
    const rowName = await findTableName('gamma');
    await userEvent.click(rowName);
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledWith('gamma', 'shared'));
  });

  it('duels a local project against a remote one', async () => {
    renderPage();
    await findTableName('gamma');
    await userEvent.click(await screen.findByRole('button', { name: 'Start a duel' }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /alpha/ }));
    await userEvent.click(await screen.findByRole('menuitem', { name: /gamma/ }));
    expect(await screen.findByText(/GAP_SOURCES/)).toBeInTheDocument();
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
    await findTableName('gamma');
    const alphaRows = screen.getAllByText('alpha')
      .filter((el) => el.classList.contains('compare-fleettable__namebtn'));
    expect(alphaRows).toHaveLength(1);
    // The local endpoint serves alpha; the shared route is only asked for
    // the genuinely remote project.
    await waitFor(() => expect(getFleetCompare.mock.calls.flat(2)).toContain('alpha'));
    expect(sharedGetFleetCompare.mock.calls.flat(2)).not.toContain('alpha');
  });

  it('leaves the fleet local-only when no shared repository is configured', async () => {
    sharedListProjects.mockRejectedValue(Object.assign(new Error('no shared repository configured'), { status: 409 }));
    renderPage();
    expect(await findTableName('alpha')).toBeInTheDocument();
    expect(screen.queryByText('gamma')).toBeNull();
    expect(screen.queryByText('remote')).toBeNull();
  });
});

// A connected evaluations repository is a comparable fleet on its own: with
// no local project at all, the published rows are ranked instead of the
// "nothing to compare" empty state.
describe('ComparePage with published projects only', () => {
  const PUBLISHED = [
    { id: 'gamma', name: 'gamma', displayName: 'gamma', languageStats: { rb: 10 }, totalFiles: 50, analyzedFiles: 50, runsCount: 1, latestDate: iso(3) },
    { id: 'delta', name: 'delta', displayName: 'delta', languageStats: { go: 20 }, totalFiles: 80, analyzedFiles: 80, runsCount: 2, latestDate: iso(1) },
  ];

  beforeEach(() => {
    sharedListProjects.mockResolvedValue({ projects: PUBLISHED, lastSynced: null, stale: false });
    sharedGetFleetCompare.mockImplementation(fleetOf((id) => (id === 'gamma' ? summary(6.5, 6.2) : summary(7.1, 6.9))));
  });

  it('ranks the published rows and never shows the empty state', async () => {
    renderPage({ projects: [] });
    expect(await findTableName('gamma')).toBeInTheDocument();
    // The leader is named in the table and again in the attention strip.
    expect(screen.getAllByText('delta').length).toBeGreaterThan(0);
    expect(screen.queryByText('Nothing to compare yet')).toBeNull();
    expect(getFleetCompare).not.toHaveBeenCalled();
  });
});
