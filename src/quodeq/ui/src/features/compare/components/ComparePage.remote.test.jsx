import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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

import { getCompareSummary } from '../../../api/index.js';
import { sharedListProjects, sharedGetCompareSummary } from '../../../api/shared.js';
import { summary, renderPage, iso } from './_comparePage.fixtures.jsx';

/**
 * Split from ComparePage.test.jsx: remote/shared-fleet projects.
 */

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
