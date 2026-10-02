import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { SHARED, makeApi, pageActions, renderPage } from './_projectsPageTeam.fixtures.jsx';

const LIMIT_COPY = 'download failed · This project is larger than the pull limit. Raise QUODEQ_MAX_ZIP_SIZE_MB and try again.';
const tooLarge = (finishedAt) => ({
  state: 'error', phase: SYNC_PHASE.ERROR, project: SHARED.id, code: 'PULL_TOO_LARGE',
  error: 'Project exceeds maximum export size of 500 MB compressed.', finishedAt,
});
const cardOf = (text) => screen.getByText(text).closest('.project-card');

afterEach(() => { vi.clearAllMocks(); });

describe('ProjectsPage — a failed pull on a team card', () => {
  it('shows the mapped failure on the card with the pull button enabled, and a new run clears it', async () => {
    const user = userEvent.setup();
    const { api, server } = makeApi({ configured: true });
    api.startPull
      .mockImplementationOnce(async (project) => {
        server.slots.pull = tooLarge(5);
        return { started: true, project };
      })
      .mockImplementationOnce(async (project) => {
        server.slots.pull = { state: 'running', phase: SYNC_PHASE.DOWNLOADING, project };
        return { started: true, project };
      });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);

    await user.click(await screen.findByRole('button', { name: 'pull local copy' }));
    const card = await waitFor(() => cardOf(LIMIT_COPY));
    const retry = within(card).getByRole('button', { name: 'pull local copy' });
    expect(retry).toBeEnabled();

    await user.click(retry);
    await waitFor(() => expect(screen.getByRole('button', { name: 'downloading…' })).toBeInTheDocument());
    expect(screen.queryByText(LIMIT_COPY)).not.toBeInTheDocument();
    expect(api.startPull).toHaveBeenCalledTimes(2);
  });

  it('while one card pulls, the other cards cannot start a second pull', async () => {
    const other = { id: 'shared-2', name: 'other-repo', publishedBy: 'bo', publishedAt: '2026-07-17T00:00:00Z' };
    const { api } = makeApi({
      configured: true,
      slots: { pull: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, project: SHARED.id } },
      sharedListProjects: vi.fn(async () => ({ projects: [SHARED, other], lastSynced: null, stale: false })),
    });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);

    await screen.findByRole('button', { name: 'downloading…' });
    expect(within(cardOf('other-repo')).getByRole('button', { name: 'pull local copy' })).toBeDisabled();
  });
});
