import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom/vitest';
import ConnectStep from './ConnectStep.jsx';
import { ApiProvider } from '../../../../api/ApiContext.jsx';
import { withQueryClient } from '../../../../test-utils/withQueryClient.jsx';

const URL = 'https://github.com/team/evals.git';

function makeApi(overrides = {}) {
  return {
    connectShared: vi.fn(async (url) => ({ started: true, url })),
    getGithubAccount: vi.fn(async () => ({})),
    probeGit: vi.fn(async () => ({ reachable: false })),
    ...overrides,
  };
}

function renderStep(api, props = {}) {
  const QC = withQueryClient();
  const handlers = { onConnectStarted: vi.fn(), ...props };
  const view = render(<QC><ApiProvider value={api}><ConnectStep {...handlers} /></ApiProvider></QC>);
  return { ...handlers, view };
}

describe('ConnectStep', () => {
  it('names the step and says where the download shows', () => {
    renderStep(makeApi());
    expect(screen.getByText('evaluations repository')).toBeInTheDocument();
    expect(screen.getByText('Paste the git address, or choose a local folder that is a git repository. Download progress shows on the Repositories tab.')).toBeInTheDocument();
  });

  it('a started connect hands over to the Repositories tab', async () => {
    const user = userEvent.setup();
    const api = makeApi();
    const { onConnectStarted } = renderStep(api);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), URL);
    await user.click(screen.getByRole('button', { name: 'connect' }));
    await waitFor(() => expect(onConnectStarted).toHaveBeenCalledTimes(1));
    expect(api.connectShared).toHaveBeenCalledWith(URL);
  });

  it('a folder that is not a git repository stays on the step with the copy under the field', async () => {
    const user = userEvent.setup();
    const refusal = Object.assign(new Error('not a git repository'), { code: 'NOT_A_GIT_REPO', status: 400 });
    const api = makeApi({ connectShared: vi.fn(async () => { throw refusal; }) });
    const { onConnectStarted } = renderStep(api);
    await user.type(screen.getByRole('textbox', { name: /evaluations repository url/i }), 'file:///Users/me/plain');
    await user.click(screen.getByRole('button', { name: 'connect' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('That folder is not a git repository. Run git init there first, or point at a bare repository.');
    expect(onConnectStarted).not.toHaveBeenCalled();
  });

  it('offers back when there is a welcome behind it', async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    renderStep(makeApi(), { onBack });
    expect(screen.queryByRole('button', { name: 'cancel' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'back' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('offers cancel when opened on its own', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderStep(makeApi(), { onCancel });
    expect(screen.queryByRole('button', { name: 'back' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'cancel' }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
