import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getCloneStatus, isCloneActive, cloneNameFromUrl } from './projectClone.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';

const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });

describe('projectClone api', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('reads the slot, converts finishedAt to ms and tells when it is active', async () => {
    fetch.mockResolvedValue(ok({ state: 'running', kind: 'clone', phase: 'downloading', percent: 45, bytes: 12582912, repo: 'https://github.com/o/repo.git', dest: '/u/quodeq/repos/repo', projectId: null, projectName: null, scanData: null, error: null, code: null, detail: null, finishedAt: 1700000000 }));
    const slot = await getCloneStatus();
    expect(fetch.mock.calls[0][0]).toMatch(/\/api\/projects\/clone-status$/);
    expect(slot.finishedAt).toBe(1700000000000);
    expect(slot.phase).toBe(SYNC_PHASE.DOWNLOADING);
    expect(isCloneActive(slot)).toBe(true);
  });

  it('names the working copy after the repository', () => {
    expect(cloneNameFromUrl('https://github.com/acme/billing.git')).toBe('billing');
    expect(cloneNameFromUrl('git@github.com:acme/billing')).toBe('billing');
    expect(cloneNameFromUrl('https://github.com/acme/')).toBe('repo');
  });
});
