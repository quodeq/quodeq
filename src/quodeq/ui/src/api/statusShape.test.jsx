import { describe, it, expect, vi, afterEach } from 'vitest';
import { getSharedStatus } from './sharedStatus.js';
import { getSyncStatus } from './syncStatus.js';

afterEach(() => vi.restoreAllMocks());

// Both readers fill ONE react-query cache entry (sharedKeys.status()), so
// whichever fetches last must leave the identical shape behind.
describe('status readers share one normalized shape', () => {
  it('getSharedStatus and getSyncStatus return deep-equal output, slots in ms and a missing slot normalized', async () => {
    const payload = {
      configured: true, url: 'u', lastSynced: 1752751800, syncing: false, publish: { state: 'idle', finishedAt: 7 },
      connect: { state: 'done', phase: 'done', finishedAt: 100 },
      refresh: { state: 'error', phase: 'error', finishedAt: 200 },
      // pull slot absent
    };
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => payload })));

    const shared = await getSharedStatus();
    const sync = await getSyncStatus();

    expect(shared).toEqual(sync);
    expect(shared.connect.finishedAt).toBe(100000);
    expect(shared.refresh.finishedAt).toBe(200000);
    expect(shared.pull).toEqual({ finishedAt: null });
    expect(shared.lastSynced).toBe(1752751800000);
    expect(shared.publish).toEqual({ state: 'idle', finishedAt: 7 });
  });
});
