import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ProjectsPage from './ProjectsPage.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { SidePaneProvider } from '../../side-pane/index.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { CLONE_CODE_PROJECT_EXISTS } from '../../../api/projectClone.js';
import { DISMISSED_CLONE_KEY } from '../hooks/useDismissedCloneFailure.js';
import { LOCAL, makeApi, pageActions } from './_projectsPageTeam.fixtures.jsx';

const REPO = 'https://github.com/acme/billing.git';
const running = { state: 'running', kind: 'clone', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912, repo: REPO, dest: '/u/quodeq/repos/billing', finishedAt: null };
const failed = { ...running, state: 'error', phase: SYNC_PHASE.ERROR, code: 'REPO_NOT_FOUND', error: 'Repository not found', finishedAt: 5 };
const done = { ...running, state: 'done', phase: SYNC_PHASE.DONE, percent: 100, finishedAt: 7 };

function setup(slot, projects = LOCAL) {
  const server = { slot };
  const { api } = makeApi({
    getCloneStatus: vi.fn(async () => server.slot),
    registerProject: vi.fn(async () => ({ started: true })),
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={client}>
      <ApiProvider value={api}><SidePaneProvider><ProjectsPage projects={projects} actions={pageActions} /></SidePaneProvider></ApiProvider>
    </QueryClientProvider>
  );
  const view = render(tree());
  return { api, server, client, view, remount: () => { view.unmount(); return render(tree()); } };
}

afterEach(() => {
  vi.clearAllMocks();
  localStorage.removeItem(DISMISSED_CLONE_KEY);
});

describe('ProjectsPage ghost tile', () => {
  it('a running clone puts the ghost tile first and shows the arriving line instead of the cards; done removes it', async () => {
    const { server, client } = setup(running, []);
    expect(await screen.findByText('billing')).toBeInTheDocument();
    expect(screen.getByText('cloning · 45% · 12.0 MB')).toBeInTheDocument();
    expect(screen.getByText('Your project will appear here when the scan finishes.')).toBeInTheDocument();

    server.slot = done;
    await client.invalidateQueries({ queryKey: projectsKeys.clone() });
    await waitFor(() => expect(screen.queryByText('billing')).not.toBeInTheDocument());
  });

  it('the card of the project being cloned stays hidden until the clone lands', async () => {
    const registered = { id: 'p-billing', name: 'billing', path: '/u/quodeq/repos/billing', latestDate: '2026-07-19T00:00:00Z' };
    const { server, client } = setup(running, [...LOCAL, registered]);
    expect(await screen.findByText('cloning · 45% · 12.0 MB')).toBeInTheDocument();
    // One "billing": the tile. The registered card (its folder does not exist yet) waits.
    expect(screen.getAllByText('billing')).toHaveLength(1);
    expect(screen.getByText('app')).toBeInTheDocument();

    server.slot = { ...done, projectId: 'p-billing' };
    await client.invalidateQueries({ queryKey: projectsKeys.clone() });
    await waitFor(() => expect(screen.queryByText(/cloning · /)).not.toBeInTheDocument());
    // Still one "billing": now the card.
    expect(screen.getAllByText('billing')).toHaveLength(1);
  });

  it('the tile heads the list of existing projects', async () => {
    setup(running);
    const tile = (await screen.findByText('billing')).closest('article');
    const cards = document.querySelector('.projects-cards');
    expect(tile.compareDocumentPosition(cards) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('a failed clone on an empty page shows the error row above the compact cards, retry re-posts to the default root', async () => {
    const user = userEvent.setup();
    const { api } = setup(failed, []);
    expect(await screen.findByText(/download failed · /)).toBeInTheDocument();
    expect(screen.queryByText('Your project will appear here when the scan finishes.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'retry' }));
    // The server derives the default root: the slot cannot recover an explicit one.
    expect(api.registerProject).toHaveBeenCalledWith({ repo: REPO });
  });

  it('a slot that ended because the project already exists shows no ghost tile', async () => {
    const exists = { ...failed, code: CLONE_CODE_PROJECT_EXISTS, error: 'A project for this repository already exists.', detail: 'p-1' };
    const { client } = setup(exists);
    await waitFor(() => expect(client.getQueryData(projectsKeys.clone())).toEqual(exists));
    expect(screen.queryByText(/download failed · /)).not.toBeInTheDocument();
    expect(screen.queryByText('billing')).not.toBeInTheDocument();
  });

  it('a dismissed failure stays hidden for the same finishedAt and shows again for a new one', async () => {
    const user = userEvent.setup();
    const { server, remount } = setup(failed);
    await user.click(await screen.findByRole('button', { name: 'close' }));
    expect(screen.queryByText(/download failed · /)).not.toBeInTheDocument();

    const again = remount();
    await waitFor(() => expect(again.container.querySelector('.projects-cards')).not.toBeNull());
    expect(screen.queryByText(/download failed · /)).not.toBeInTheDocument();

    server.slot = { ...failed, finishedAt: 9 };
    again.unmount();
    setupAgain(server);
    expect(await screen.findByText(/download failed · /)).toBeInTheDocument();
  });
});

function setupAgain(server) {
  const { api } = makeApi({ getCloneStatus: vi.fn(async () => server.slot) });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ApiProvider value={api}><SidePaneProvider><ProjectsPage projects={LOCAL} actions={pageActions} /></SidePaneProvider></ApiProvider>
    </QueryClientProvider>,
  );
}
