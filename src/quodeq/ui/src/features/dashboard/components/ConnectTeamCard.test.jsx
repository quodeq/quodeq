import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ConnectTeamCard from './ConnectTeamCard.jsx';
import { useSharedProjects } from '../hooks/useSharedProjects.js';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SYNC_PHASE } from '../../../vocab/syncPhase.js';

const idle = { state: 'idle', phase: null };
const unconfigured = { configured: false, url: null, lastSynced: null, connect: idle, refresh: idle, pull: idle };

function makeApi(overrides = {}) {
  return {
    getSyncStatus: vi.fn(async () => unconfigured),
    getSharedStatus: vi.fn(async () => unconfigured),
    sharedListProjects: vi.fn(async () => ({ projects: [], lastSynced: null, stale: false })),
    connectShared: vi.fn(async (url) => ({ started: true, url })),
    startRefresh: vi.fn(async () => ({ started: true })),
    startPull: vi.fn(async () => ({ started: true })),
    getGithubAccount: vi.fn(async () => ({ signInAvailable: false, ghAvailable: false, ghLoggedIn: false })),
    probeGit: vi.fn(async () => ({ reachable: false })),
    ...overrides,
  };
}

// The card as ProjectsPage mounts it: fed by useSharedProjects, the screen's one status poll.
function Harness() {
  const shared = useSharedProjects();
  return (
    <ConnectTeamCard
      onConnect={shared.connect}
      connecting={shared.connecting}
      error={shared.connectError}
      accessFailure={shared.accessFailure}
    />
  );
}

function renderCard(api) {
  const QC = withQueryClient();
  return render(<QC><ApiProvider value={api}><Harness /></ApiProvider></QC>);
}

describe('ConnectTeamCard', () => {
  it('shows the title and the description', async () => {
    renderCard(makeApi());
    expect(screen.getByText('evaluations repository')).toBeInTheDocument();
    expect(screen.getByText("A git repository where evaluations are published, yours or your team's. Connect it to browse them next to your own projects.")).toBeInTheDocument();
  });

  it('typing a URL and pressing connect calls connectShared with it', async () => {
    const api = makeApi();
    const user = userEvent.setup();
    renderCard(api);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), '  https://github.com/team/results.git ');
    await user.click(screen.getByRole('button', { name: 'connect' }));
    await waitFor(() => expect(api.connectShared).toHaveBeenCalledWith('https://github.com/team/results.git'));
    expect(api.connectShared).toHaveBeenCalledTimes(1);
  });

  it('connect does nothing with an empty field', async () => {
    const api = makeApi();
    const user = userEvent.setup();
    renderCard(api);
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(api.connectShared).not.toHaveBeenCalled();
  });

  it('Enter in the field connects too', async () => {
    const api = makeApi();
    const user = userEvent.setup();
    renderCard(api);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), 'https://github.com/team/results.git{Enter}');
    await waitFor(() => expect(api.connectShared).toHaveBeenCalledWith('https://github.com/team/results.git'));
  });

  it('an ACCESS_ rejection renders the access panel under the field', async () => {
    const refusal = Object.assign(new Error('auth required'), {
      code: 'ACCESS_AUTH_REQUIRED',
      body: { kind: 'auth_required', detail: '', host: 'github.com', isGitHub: true, cloneUrl: '' },
    });
    const api = makeApi({ connectShared: vi.fn(async () => { throw refusal; }) });
    const user = userEvent.setup();
    const { container } = renderCard(api);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), 'https://github.com/team/private.git');
    await user.click(screen.getByRole('button', { name: 'connect' }));
    await waitFor(() => expect(container.querySelector('.connect-team-card .access-panel')).toBeInTheDocument());
    // The panel replaces the plain error line; the raw message is not shown twice.
    expect(screen.queryByText('auth required')).not.toBeInTheDocument();
  });

  it('a connect slot in ERROR with FOREIGN_REPO shows the mapped copy under the field', async () => {
    const failed = { ...unconfigured, connect: { state: 'error', phase: SYNC_PHASE.ERROR, code: 'FOREIGN_REPO', error: 'raw server text' } };
    renderCard(makeApi({ getSyncStatus: vi.fn(async () => failed), getSharedStatus: vi.fn(async () => failed) }));
    expect(await screen.findByText('That address is not a quodeq evaluations repository. It needs a quodeq.json and an evaluations folder.')).toBeInTheDocument();
    expect(screen.queryByText('raw server text')).not.toBeInTheDocument();
  });

  it('disables the field and the button while the connect job runs', async () => {
    const running = { ...unconfigured, connect: { state: 'running', phase: SYNC_PHASE.DOWNLOADING, percent: 10 } };
    renderCard(makeApi({ getSyncStatus: vi.fn(async () => running), getSharedStatus: vi.fn(async () => running) }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'connecting…' })).toBeDisabled());
    expect(screen.getByRole('textbox', { name: /evaluations repository url/i })).toBeDisabled();
  });
});

describe('ConnectTeamCard close', () => {
  it('renders "close" only with onClose, and calls it', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(<ConnectTeamCard onConnect={vi.fn()} />);
    expect(screen.queryByRole('button', { name: 'close' })).not.toBeInTheDocument();
    rerender(<ConnectTeamCard onConnect={vi.fn()} onClose={onClose} />);
    await user.click(screen.getByRole('button', { name: 'close' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
