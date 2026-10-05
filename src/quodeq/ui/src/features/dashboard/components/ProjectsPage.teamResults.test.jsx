import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import { useQuery } from '@tanstack/react-query';
import ProjectsPage from './ProjectsPage.jsx';
import { useApi } from '../../../api/ApiContext.jsx';
import { projectsKeys } from '../../../api/queryKeys.js';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';
import { confirmDialog } from '../../../utils/confirmDialog.js';
import { copyToClipboard } from '../../../utils/clipboard.js';
import { URL, LOCAL, makeApi, pageActions, renderPage } from './_projectsPageTeam.fixtures.jsx';

vi.mock('../../../utils/confirmDialog.js', () => ({ confirmDialog: vi.fn(async () => true) }));
// copyToClipboard resolves false when the webview has no clipboard (see its own tests).
vi.mock('../../../utils/clipboard.js', () => ({ copyToClipboard: vi.fn(async () => true) }));

afterEach(() => { vi.clearAllMocks(); });

describe('ProjectsPage — header actions', () => {
  it('shows add project and a more menu with add evaluations repository and import project while nothing is connected', async () => {
    const user = userEvent.setup();
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(api.getSyncStatus).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'connect evaluations repository' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'more ways to add' }));
    expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['add evaluations repository', 'import project']);
  });

  it('once a repository is configured the menu reads change repository, and the header counts both sides', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('1 local · 1 published')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'more ways to add' }));
    expect(screen.getAllByRole('menuitem').map((m) => m.textContent)).toEqual(['change repository', 'import project']);
  });

  it('"add evaluations repository" opens the connect step, not an inline card', async () => {
    const user = userEvent.setup();
    const onConnectEvaluations = vi.fn();
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={{ ...pageActions, onConnectEvaluations }} />);
    await user.click(await screen.findByRole('button', { name: 'more ways to add' }));
    await user.click(screen.getByRole('menuitem', { name: 'add evaluations repository' }));
    expect(onConnectEvaluations).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('textbox', { name: /evaluations repository url/i })).not.toBeInTheDocument();
  });

  it('"import project" in the menu runs the import, connected or not', async () => {
    const user = userEvent.setup();
    const onImportProject = vi.fn();
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={LOCAL} actions={{ ...pageActions, onImportProject }} />);
    await user.click(await screen.findByRole('button', { name: 'more ways to add' }));
    await user.click(screen.getByRole('menuitem', { name: 'import project' }));
    expect(onImportProject).toHaveBeenCalledTimes(1);
  });

  it('while a connect reads, one placeholder card per project found heads the list', async () => {
    const reading = { state: 'running', phase: SYNC_PHASE.READING, percent: null, projectsFound: 3, url: URL };
    const { api } = makeApi({ slots: { connect: reading } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('reading projects · 3 found…')).toBeInTheDocument());
    expect(document.querySelectorAll('.project-card--placeholder')).toHaveLength(3);
    // One announcement comes from the strip; the placeholders themselves are silent.
    expect(document.querySelector('.projects-cards--placeholders')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByText('app')).toBeInTheDocument();
  });

  it('a running first connect shows its progress in the strip, with no form', async () => {
    const running = { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 45, bytes: 12582912, url: URL };
    const { api } = makeApi({ slots: { connect: running } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText('downloading evaluations · 45% · 12.0 MB')).toBeInTheDocument());
    expect(screen.getByRole('progressbar', { name: 'evaluations repository sync progress' })).toHaveAttribute('aria-valuenow', '45');
    expect(screen.queryByRole('textbox', { name: /evaluations repository url/i })).not.toBeInTheDocument();
  });
});

describe('ProjectsPage — the empty page', () => {
  it('keeps the header actions and says there is nothing yet; no cards, no inline connect form', async () => {
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={[]} actions={pageActions} />);
    await waitFor(() => expect(screen.getByText(/No repositories yet\./)).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Add project' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'more ways to add' })).toBeInTheDocument();
    expect(screen.queryByText('A repository')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'start' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /evaluations repository url/i })).not.toBeInTheDocument();
  });

  it('add project opens the add panel, and the menu connects or imports', async () => {
    const user = userEvent.setup();
    const actions = { onAddProject: vi.fn(), onImportProject: vi.fn(), onConnectEvaluations: vi.fn() };
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={[]} actions={actions} />);
    await user.click(await screen.findByRole('button', { name: 'Add project' }));
    await user.click(screen.getByRole('button', { name: 'more ways to add' }));
    await user.click(screen.getByRole('menuitem', { name: 'add evaluations repository' }));
    await user.click(screen.getByRole('button', { name: 'more ways to add' }));
    await user.click(screen.getByRole('menuitem', { name: 'import project' }));
    expect(actions.onAddProject).toHaveBeenCalledTimes(1);
    expect(actions.onConnectEvaluations).toHaveBeenCalledTimes(1);
    expect(actions.onImportProject).toHaveBeenCalledTimes(1);
  });

  it('while an evaluation runs, add project reads as blocked and says why', async () => {
    const { api } = makeApi();
    renderPage(api, <ProjectsPage projects={[]} isEvaluating actions={pageActions} />);
    const add = await screen.findByRole('button', { name: 'Add project' });
    expect(add).toHaveAttribute('aria-disabled', 'true');
    expect(add).toHaveAttribute('title', 'Cannot add a project while an evaluation is running');
  });
});

// A failed connect is reported by the card only; the strip keeps the working repository.
describe('ProjectsPage — a failed connect', () => {
  const foreign = { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO', url: 'https://github.com/team/other.git', finishedAt: 5 };

  it('with nothing configured, opens the card with the error and the failed URL, so connect retries it (no lastConnectUrl needed)', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ slots: { connect: foreign } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    expect(await screen.findByText('That address is not a quodeq evaluations repository. It needs a quodeq.json and an evaluations folder.')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toHaveValue(foreign.url);
    await user.click(screen.getByRole('button', { name: 'connect' }));
    await waitFor(() => expect(api.connectShared).toHaveBeenCalledWith(foreign.url));
  });

  // A change started from the connect step lands here: the strip keeps the
  // working repository and the failure shows once, in the card.
  it('with a repository configured, the strip stays on synced and the error shows once, in the card', async () => {
    const { api } = makeApi({ configured: true, slots: { connect: foreign } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    expect(await screen.findByText('1 project · synced 2 min ago')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'update evaluations repository' })).toBeInTheDocument();
    expect(await screen.findAllByText('That address is not a quodeq evaluations repository. It needs a quodeq.json and an evaluations folder.')).toHaveLength(1);
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toHaveValue(foreign.url);
  });

  it('a folder that is not a git repository comes back with its copy and the folder kept', async () => {
    const plain = { state: 'error', phase: SYNC_PHASE.ERROR, code: 'NOT_A_GIT_REPO', url: 'file:///Users/me/plain', finishedAt: 6 };
    const { api } = makeApi({ slots: { connect: plain } });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('That folder is not a git repository. Run git init there first, or point at a bare repository.');
    expect(screen.getByText('/Users/me/plain')).toBeInTheDocument();
  });
});

describe('ProjectsPage — sync strip actions', () => {
  it('copy invite fetches the invite and flashes "copied"', async () => {
    const user = userEvent.setup();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'copy invite' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'copied' })).toBeInTheDocument());
    expect(copyToClipboard).toHaveBeenCalledWith(`Open quodeq, go to Repositories, choose more › add evaluations repository and paste ${URL}`);
  });

  it('without a clipboard the invite text shows inline, read-only', async () => {
    const user = userEvent.setup();
    copyToClipboard.mockResolvedValueOnce(false);
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={pageActions} />);
    await user.click(await screen.findByRole('button', { name: 'copy invite' }));
    const field = await screen.findByRole('textbox', { name: 'invite text for others' });
    expect(field).toHaveValue(`Open quodeq, go to Repositories, choose more › add evaluations repository and paste ${URL}`);
    expect(field).toHaveAttribute('readonly');
  });

  it('change repository opens the connect step while configured', async () => {
    const user = userEvent.setup();
    const onConnectEvaluations = vi.fn();
    const { api } = makeApi({ configured: true });
    renderPage(api, <ProjectsPage projects={LOCAL} actions={{ ...pageActions, onConnectEvaluations }} />);
    await user.click(await screen.findByRole('button', { name: 'more repository actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'change repository' }));
    expect(onConnectEvaluations).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('textbox', { name: /evaluations repository url/i })).not.toBeInTheDocument();
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
    await user.click(screen.getByRole('button', { name: 'update evaluations repository' })); // re-reads the status
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
