import { vi } from 'vitest';
import { render } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import SharedRepoSection from './SharedRepoSection.jsx';

/**
 * Shared fixtures for SharedRepoSection.*.test.jsx siblings.
 *
 * Split out of SharedRepoSection.test.jsx.
 */

export function makeFakeApi(overrides = {}) {
  const api = {
    getSharedStatus: vi.fn(async () => ({ configured: false, url: null })),
    connectShared: vi.fn(async (url) => ({ started: true, url })),
    startRefresh: vi.fn(async () => ({ started: true })),
    startPull: vi.fn(async (project) => ({ started: true, project })),
    getInvite: vi.fn(async () => ({ text: '' })),
    disconnectShared: vi.fn(async () => ({ configured: false })),
    probeGit: vi.fn(),
    getGithubAccount: vi.fn(),
    startDeviceFlow: vi.fn(),
    getDeviceFlow: vi.fn(),
    pasteGithubToken: vi.fn(),
    ...overrides,
  };
  // SharedRepoSection polls getSyncStatus; these tests set the status through getSharedStatus.
  return { getSyncStatus: (...a) => api.getSharedStatus(...a), ...api };
}

export function renderWithApi(fakeApi, props = {}) {
  const QC = withQueryClient();
  return render(
    <QC>
      <ApiProvider value={fakeApi}><SharedRepoSection {...props} /></ApiProvider>
    </QC>
  );
}
