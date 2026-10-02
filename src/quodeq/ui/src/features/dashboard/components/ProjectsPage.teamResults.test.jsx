import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import { useQuery } from '@tanstack/react-query';
import ProjectsPage from './ProjectsPage.jsx';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider, useApi } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { SidePaneProvider } from '../../side-pane/index.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { copyToClipboard } from '../../../utils/clipboard.js';

vi.mock('../../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn(async () => true) }));
// copyToClipboard resolves false when the webview has no clipboard (see its own tests).
vi.mock('../../../utils/clipboard.js', () => ({ copyToClipboard: vi.fn(async () => true) }));

const URL = 'https://github.com/team/results.git';
const idle = { state: 'idle', phase: null };
const SHARED = { id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' };

// The fake server: `slots` and `configured` are mutable so a test can move a job along.
function makeApi({ configured = false, slots = {}, ...overrides } = {}) {
  const server = { configured, slots: { connect: idle, refresh: idle, pull: idle, ...slots } };
  const status = vi.fn(async () => ({
    configured: server.configured, url: server.configured ? URL : null, lastSynced: Date.now() - 120000, ...server.slots,
  }));
  const api = {
    getSharedStatus: status,
    getSyncStatus: status,
    sharedListProjects: vi.fn(async () => ({ projects: server.configured ? [SHARED] : [], lastSynced: null, stale: false })),
    connectShared: vi.fn(async (url) => ({ started: true, url })),
    disconnectShared: vi.fn(async () => ({ configured: false })),
    startRefresh: vi.fn(async () => ({ started: true })),
    startPull: vi.fn(async (id) => ({ started: true, project: id })),
    publishProject: vi.fn(async () => ({ started: true })),
    getInvite: vi.fn(async () => ({ text: `Open quodeq, choose Join your team's results, paste ${URL}` })),
    getGithubAccount: vi.fn(async () => ({})),
    probeGit: vi.fn(async () => ({ reachable: false })),
    ...overrides,
  };
  return { api, server };
}

function renderPage(api, ui) {
  const QC = withQueryClient();
  return render(<QC><ApiProvider value={api}><SidePaneProvider>{ui}</SidePaneProvider></ApiProvider></QC>);
}

const LOCAL = [{ id: 'a', name: 'app', latestDate: '2026-07-19T00:00:00Z' }];
const pageActions = { onAddProject: vi.fn(), onImportProject: vi.fn() };

afterEach(() => { vi.clearAllMocks(); });

describe('ProjectsPage — header actions and the connect card', () => {
  it('shows import, connect team results and add project while nothing is connected', async () => {
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(api.getSyncStatus).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'Import project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'connect team results' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
  });

  it('drops "connect team results" once a repository is configured, and counts both sides', async () => {
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('1 local · 1 from your team')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'connect team results' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Import project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
  });

  it('"connect team results" toggles the connect card', async () => {
    const user = userEvent.setup();
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    const toggle = await screen.findByRole('button', { name: 'connect team results' });
    expect(screen.queryByText('team results')).not.toBeInTheDocument();
    await user.click(toggle);
    expect(screen.getByText('team results')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await user.click(toggle);
    expect(screen.queryByText('team results')).not.toBeInTheDocument();
  });

  it('an empty page with nothing connected always shows the connect card next to the add-first call to action', async () => {
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('team results')).toBeInTheDocument());
    expect(screen.getByText('Add your first project')).toBeInTheDocument();
  });

  it('a first connect shows its progress in the strip before the repository is configured', async () => {
    const user = userEvent.setup();
    const { api, server } = makeApi({
      connectShared: vi.fn(async (url) => {
        server.slots.connect = { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912, url };
        return { started: true, url };
      }),
    });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    await user.type(await screen.findByRole('textbox', { name: /team results repository url/i }), URL);
    await user.click(screen.getByRole('button', { name: 'connect' }));

    await waitFor(() => expect(screen.getByText('downloading evaluations · 45% · 12.0 MB')).toBeInTheDocument());
    expect(api.connectShared).toHaveBeenCalledWith(URL);
    expect(screen.getByRole('progressbar', { name: 'team results sync progress' })).toHaveAttribute('aria-valuenow', '45');
    expect(screen.getByRole('button', { name: 'connecting…' })).toBeDisabled();
  });
});

describe('ProjectsPage — sync strip actions', () => {
  it('copy invite fetches the invite and flashes "copied"', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'copy invite' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'copied' })).toBeInTheDocument());
    expect(copyToClipboard).toHaveBeenCalledWith(`Open quodeq, choose Join your team's results, paste ${URL}`);
  });

  it('without a clipboard the invite text shows inline, read-only', async () => {
    const user = userEvent.setup();
    copyToClipboard.mockResolvedValueOnce(false);
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'copy invite' }));
    const field = await screen.findByRole('textbox', { name: 'invite text for teammates' });
    expect(field).toHaveValue(`Open quodeq, choose Join your team's results, paste ${URL}`);
    expect(field).toHaveAttribute('readonly');
  });

  it('change repository opens the connect card while configured', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'more repository actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'change repository' }));
    expect(screen.getByRole('textbox', { name: /team results repository url/i })).toBeInTheDocument();
  });

  it('disconnect confirms, calls the API and hands the selection back to the app', async () => {
    const user = userEvent.setup();
    const onSharedDisconnected = vi.fn();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={{ ...pageActions, onSharedDisconnected }} />);
    await user.click(await screen.findByRole('button', { name: 'more repository actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'disconnect' }));
    await waitFor(() => expect(api.disconnectShared).toHaveBeenCalledTimes(1));
    expect(confirmDialog).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(onSharedDisconnected).toHaveBeenCalled());
  });

  it('a status poll that fails over a configured repository shows offline with the last sync', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await screen.findByText('1 project · synced 2 min ago');
    api.getSyncStatus.mockRejectedValue(new Error('offline'));
    await user.click(screen.getByRole('button', { name: 'update team results' })); // re-reads the status
    await waitFor(() => expect(screen.getByText('offline · showing results from 2 min ago')).toBeInTheDocument());
  });
});

// ProjectsPage as the app mounts it: the local list comes from the projects query.
function AppLikePage() {
  const { getProjects } = useApi();
  const { data = [] } = useQuery({ queryKey: projectsKeys.list(), queryFn: getProjects });
  return <ProjectsPage projects={data} actions={pageActions} />;
}

describe('ProjectsPage — pull state on team cards', () => {
  it('a team card shows "downloading…" while the pull slot points at it', async () => {
    const { api } = makeApi({ configured: true, slots: { pull: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, project: 'shared-1' } } });
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    const btn = await screen.findByRole('button', { name: 'downloading…' });
    expect(btn).toBeDisabled();
    const card = btn.closest('.project-card');
    expect(within(card).getByRole('progressbar')).toHaveAttribute('aria-busy', 'true');
  });

  it('the local list gains the pulled project once the pull is done, through the query invalidation alone', async () => {
    const user = userEvent.setup();
    const pulled = { id: 'local-9', name: 'demo-repo-copy', latestDate: '2026-07-20T00:00:00Z' };
    let local = [];
    const { api, server } = makeApi({
      configured: true,
      getProjects: vi.fn(async () => local),
      startPull: vi.fn(async (project) => {
        local = [pulled];
        server.slots.pull = { state: 'done', phase: SYNC_PHASE.DONE, project, projectId: pulled.id, finishedAt: 5 };
        return { started: true, project };
      }),
    });
    renderPage(api, <AppLikePage />);
    await user.click(await screen.findByRole('button', { name: 'pull local copy' }));
    await waitFor(() => expect(screen.getByText('demo-repo-copy')).toBeInTheDocument());
    expect(screen.getByText('pulled to local')).toBeInTheDocument();
  });
});
