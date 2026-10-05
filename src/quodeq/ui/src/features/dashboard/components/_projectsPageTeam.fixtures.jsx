import { vi } from 'vitest';
import { render } from '@testing-library/react';
import { withQueryClient } from '../../../test-utils/withQueryClient.jsx';
import { ApiProvider } from '../../../api/ApiContext.jsx';
import { SidePaneProvider } from '../../side-pane/index.js';

/** Shared fixtures for the ProjectsPage team-results tests (ProjectsPage.teamResults*.test.jsx). */

export const URL = 'https://github.com/team/results.git';
export const idle = { state: 'idle', phase: null };
export const SHARED = { id: 'shared-1', name: 'demo-repo', publishedBy: 'ana', publishedAt: '2026-07-16T00:00:00Z' };

// The fake server: `slots` and `configured` are mutable so a test can move a job along.
export function makeApi({ configured = false, slots = {}, ...overrides } = {}) {
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
    getInvite: vi.fn(async () => ({ text: `Open quodeq, on Repositories choose more › add evaluations repository, paste ${URL}` })),
    getGithubAccount: vi.fn(async () => ({})),
    probeGit: vi.fn(async () => ({ reachable: false })),
    ...overrides,
  };
  return { api, server };
}

export function renderPage(api, ui) {
  const QC = withQueryClient();
  return render(<QC><ApiProvider value={api}><SidePaneProvider>{ui}</SidePaneProvider></ApiProvider></QC>);
}

export const LOCAL = [{ id: 'a', name: 'app', latestDate: '2026-07-19T00:00:00Z' }];
export const pageActions = { onAddProject: vi.fn(), onImportProject: vi.fn(), onConnectEvaluations: vi.fn() };
