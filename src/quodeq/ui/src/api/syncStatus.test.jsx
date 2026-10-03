import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { getSyncStatus, startRefresh, startPull, getInvite, isSlotActive, anyActive } from './syncStatus.js';
import { SYNC_PHASE } from '../vocab/syncPhase.js';

const ok = (payload) => ({ ok: true, status: 200, json: async () => payload });

describe('syncStatus api', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); });
  afterEach(() => { vi.unstubAllGlobals(); });

  it('normalises the three slots and converts seconds to ms', async () => {
    fetch.mockResolvedValue(ok({
      configured: true, url: 'u', lastSynced: 1700000000, repoState: 'ok', syncing: true,
      connect: { state: 'running', kind: 'connect', phase: 'downloading', percent: 45, bytes: 12, projectsFound: null, error: null, code: null, finishedAt: null },
      refresh: { state: 'idle', kind: null, phase: null, percent: null, bytes: null, projectsFound: null, error: null, code: null, finishedAt: 1700000100 },
      pull: { state: 'idle', phase: null, project: null, projectId: null, projectName: null, renamed: null, finishedAt: null },
    }));
    const s = await getSyncStatus();
    expect(s.lastSynced).toBe(1700000000000);
    expect(s.refresh.finishedAt).toBe(1700000100000);
    expect(s.connect.phase).toBe(SYNC_PHASE.DOWNLOADING);
    expect(isSlotActive(s.connect)).toBe(true);
    expect(isSlotActive(s.refresh)).toBe(false);
    expect(anyActive(s)).toBe(true);
  });

  it('posts refresh, pull and gets the invite', async () => {
    fetch.mockResolvedValue(ok({ started: true }));
    await startRefresh();
    await startPull('abc', 'copy');
    fetch.mockResolvedValue(ok({ text: 'Open quodeq…' }));
    const invite = await getInvite();
    const calls = fetch.mock.calls.map(([u, i]) => `${i?.method || 'GET'} ${u.replace(/^.*\/api/, '')}`);
    expect(calls).toEqual(['POST /shared/refresh', 'POST /shared/projects/abc/pull', 'GET /shared/invite']);
    expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({ action: 'copy' });
    expect(invite.text).toMatch(/^Open quodeq/);
  });
});
