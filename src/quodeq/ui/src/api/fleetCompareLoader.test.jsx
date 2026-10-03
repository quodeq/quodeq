import { describe, it, expect, vi } from 'vitest';
import { makeFleetCompareLoader } from './fleetCompareLoader.js';
import { t } from '../strings/index.js';

const fleetOf = (ids, errors = {}) => ({
  summaries: ids.filter((id) => !errors[id]).map((id) => ({ project: id })),
  errors,
});

describe('makeFleetCompareLoader', () => {
  it('joins lookups started in the same tick into one fleet request', async () => {
    const fetchFleet = vi.fn(async (ids) => fleetOf(ids));
    const load = makeFleetCompareLoader(fetchFleet);
    const results = await Promise.all([load('a'), load('b'), load('a')]);
    expect(fetchFleet).toHaveBeenCalledTimes(1);
    expect(fetchFleet).toHaveBeenCalledWith(['a', 'b']);
    expect(results.map((s) => s.project)).toEqual(['a', 'b', 'a']);
  });

  it('settles each project from its own entry: summary, server error, or the generic failure', async () => {
    const load = makeFleetCompareLoader(async (ids) => fleetOf(ids, { b: 'Failed to load compare summary' }));
    const [a, b, c] = await Promise.allSettled([load('a'), load('b'), load('c')]);
    expect(a).toEqual({ status: 'fulfilled', value: { project: 'a' } });
    expect(b.reason.message).toBe('Failed to load compare summary');
    expect(c.status).toBe('fulfilled');
    const missing = makeFleetCompareLoader(async () => ({ summaries: [], errors: {} }));
    await expect(missing('ghost')).rejects.toThrow(t('compare.loadFailed'));
  });

  it('rejects every waiter when the fleet request itself fails', async () => {
    const load = makeFleetCompareLoader(async () => { throw new Error('offline'); });
    const settled = await Promise.allSettled([load('a'), load('b')]);
    expect(settled.map((s) => s.reason.message)).toEqual(['offline', 'offline']);
  });

  it('starts a new batch for lookups after the flush', async () => {
    const fetchFleet = vi.fn(async (ids) => fleetOf(ids));
    const load = makeFleetCompareLoader(fetchFleet);
    await load('a');
    await load('b');
    expect(fetchFleet.mock.calls).toEqual([[['a']], [['b']]]);
  });
});
