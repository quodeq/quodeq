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

  it('the tile heads the list of existing projects', async () => {
    setup(running);
    const tile = (await screen.findByText('billing')).closest('article');
    const cards = document.querySelector('.projects-cards');
    expect(tile.compareDocumentPosition(cards) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('a failed clone on an empty page shows the error row above the compact cards, retry re-posts into the parent folder', async () => {
    const user = userEvent.setup();
    const { api } = setup(failed, []);
    expect(await screen.findByText(/download failed · /)).toBeInTheDocument();
    expect(screen.queryByText('Your project will appear here when the scan finishes.')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'retry' }));
    expect(api.registerProject).toHaveBeenCalledWith({ repo: REPO, cloneDest: '/u/quodeq/repos' });
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
