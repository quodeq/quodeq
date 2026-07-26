import { beforeEach, expect, it, vi } from 'vitest';
import { VISIBLE_STANDARDS_STORAGE_KEY, DEFAULT_VISIBLE_STANDARDS } from '../constants.js';

vi.mock('../api/standards.js', () => ({
  getStandardsVisibility: vi.fn(),
  putStandardsVisibility: vi.fn(),
}));

// Imported AFTER vi.mock so the mocked bindings are the ones under test.
const { getStandardsVisibility, putStandardsVisibility } = await import('../api/standards.js');
const { hydrateVisibleStandardIds, readVisibleStandardIds } =
  await import('./visibleStandards.js');

function fakeStorage(initial = {}) {
  const map = { ...initial };
  return {
    getItem: (k) => (k in map ? map[k] : null),
    setItem: (k, v) => { map[k] = v; },
    _map: map,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

it('caches the server selection into storage', async () => {
  getStandardsVisibility.mockResolvedValue({
    visibleStandardIds: ['security'], isDefault: false,
  });
  const storage = fakeStorage();
  const ids = await hydrateVisibleStandardIds('p1', { storage });
  expect(ids).toEqual(['security']);
  expect(JSON.parse(storage._map[VISIBLE_STANDARDS_STORAGE_KEY])).toEqual(['security']);
});

it('migrates an existing local selection up to the server once', async () => {
  getStandardsVisibility.mockResolvedValue({
    visibleStandardIds: [...DEFAULT_VISIBLE_STANDARDS], isDefault: true,
  });
  putStandardsVisibility.mockResolvedValue({
    visibleStandardIds: ['security'], isDefault: false,
  });
  const storage = fakeStorage({
    [VISIBLE_STANDARDS_STORAGE_KEY]: JSON.stringify(['security']),
  });
  const ids = await hydrateVisibleStandardIds('p1', { storage });
  expect(putStandardsVisibility).toHaveBeenCalledWith('p1', ['security']);
  expect(ids).toEqual(['security']);
});

it('does not migrate when the server already has a saved selection', async () => {
  getStandardsVisibility.mockResolvedValue({
    visibleStandardIds: ['reliability'], isDefault: false,
  });
  const storage = fakeStorage({
    [VISIBLE_STANDARDS_STORAGE_KEY]: JSON.stringify(['security']),
  });
  const ids = await hydrateVisibleStandardIds('p1', { storage });
  expect(putStandardsVisibility).not.toHaveBeenCalled();
  expect(ids).toEqual(['reliability']);
});

it('leaves the cached value in place when the request fails', async () => {
  getStandardsVisibility.mockRejectedValue(new Error('offline'));
  const storage = fakeStorage({
    [VISIBLE_STANDARDS_STORAGE_KEY]: JSON.stringify(['security']),
  });
  const ids = await hydrateVisibleStandardIds('p1', { storage });
  expect(ids).toEqual(['security']);
  expect(readVisibleStandardIds(storage)).toEqual(['security']);
});
