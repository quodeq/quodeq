import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ProjectsPage from './ProjectsPage.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { DISMISSED_CONNECT_KEY } from '../hooks/useDismissedConnectFailure.js';
import { LOCAL, makeApi, pageActions, renderPage } from './_projectsPageTeam.fixtures.jsx';

const FOREIGN_COPY = 'That address is not a quodeq results repository. It needs a quodeq.json and an evaluations folder.';
const foreign = { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO', url: 'https://github.com/team/other.git', finishedAt: 5 };
const urlField = () => screen.queryByRole('textbox', { name: /evaluations repository url/i });

afterEach(() => {
  vi.clearAllMocks();
  localStorage.removeItem(DISMISSED_CONNECT_KEY);
});

describe('ProjectsPage — closing a failed connect', () => {
  it('configured: a failed "change repository" card closes with "close"', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true, slots: { connect: foreign } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'more repository actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'change repository' }));
    expect(screen.getByText(FOREIGN_COPY)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'close' }));
    expect(urlField()).not.toBeInTheDocument();
    expect(screen.queryByText(FOREIGN_COPY)).not.toBeInTheDocument();
  });

  it('unconfigured with local projects: close hides a stale failure, and it stays hidden for the same finishedAt', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ slots: { connect: foreign } });
    const view = renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    expect(await screen.findByText(FOREIGN_COPY)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'close' }));
    expect(urlField()).not.toBeInTheDocument();

    // Reopened on purpose, the card no longer carries the closed failure.
    const toggle = screen.getByRole('button', { name: 'connect evaluations repository' });
    await user.click(toggle);
    expect(urlField()).toBeInTheDocument();
    expect(screen.queryByText(FOREIGN_COPY)).not.toBeInTheDocument();

    // A fresh mount (the next visit) reads the same slot and keeps it closed.
    view.unmount();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(api.getSyncStatus.mock.calls.length).toBeGreaterThanOrEqual(2));
    await screen.findByRole('button', { name: 'connect evaluations repository' });
    expect(urlField()).not.toBeInTheDocument();
    expect(screen.queryByText(FOREIGN_COPY)).not.toBeInTheDocument();
  });

  it('a new failure (a later finishedAt) shows again after one was closed', async () => {
    const user = userEvent.setup();
    const { api, server } = makeApi({ slots: { connect: foreign } });
    const view = renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'close' }));
    expect(urlField()).not.toBeInTheDocument();

    server.slots.connect = { ...foreign, finishedAt: 9 };
    view.unmount();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    expect(await screen.findByText(FOREIGN_COPY)).toBeInTheDocument();
    expect(urlField()).toHaveValue(foreign.url);
  });

  it('on an empty page the card stays as the connect entry and only its error closes', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ slots: { connect: foreign } });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    expect(await screen.findByText(FOREIGN_COPY)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'close' }));
    expect(screen.queryByText(FOREIGN_COPY)).not.toBeInTheDocument();
    expect(urlField()).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'close' })).not.toBeInTheDocument();
  });
});

describe('ProjectsPage — an empty page while a connect reads the team projects', () => {
  it('says the results are on their way instead of "add your first project", then shows the cards at DONE', async () => {
    const reading = { state: 'running', phase: SYNC_PHASE.READING, projectsFound: 1, url: 'u' };
    const { api, server } = makeApi({ configured: true, slots: { connect: reading } });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);

    expect(await screen.findByText("Published evaluations will appear here when reading finishes.")).toBeInTheDocument();
    expect(screen.queryByText('Add your first project')).not.toBeInTheDocument();

    server.slots.connect = { state: 'done', phase: SYNC_PHASE.DONE, projectsFound: 1, finishedAt: 8 };
    await waitFor(() => expect(screen.getByText('demo-repo')).toBeInTheDocument(), { timeout: 4000 });
    expect(screen.queryByText("Published evaluations will appear here when reading finishes.")).not.toBeInTheDocument();
    expect(screen.queryByText('Add your first project')).not.toBeInTheDocument();
  });
});
