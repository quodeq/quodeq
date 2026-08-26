import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { VISIBLE_STANDARDS_STORAGE_KEY } from '../../../constants.js';

vi.mock('../../../api/standards.js', () => ({
  putStandardsVisibility: vi.fn(),
}));

// Imported AFTER vi.mock so the mocked binding is the one under test —
// vi.spyOn on the module object does not intercept a direct named import
// under ESM (visibleStandards.js/useVisibleStandards.js bind
// putStandardsVisibility at import time).
const api = await import('../../../api/standards.js');
const { useVisibleStandards } = await import('./useVisibleStandards.js');
const { withQueryClient } = await import('../../../test-utils/withQueryClient.jsx');

function fakeStorage(initial = {}) {
  const map = { ...initial };
  return {
    getItem: (k) => (k in map ? map[k] : null),
    setItem: (k, v) => { map[k] = v; },
    _map: map,
  };
}

describe('useVisibleStandards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 'security' is one of DEFAULT_VISIBLE_STANDARDS (constants.js), so the
  // hook's initial state already contains it. Use a non-default id here to
  // exercise add/remove/toggle without fighting that default.
  it('toggle adds and removes ids, persisting to storage', () => {
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage }), { wrapper: withQueryClient() });
    act(() => result.current.toggle('custom-standard'));
    expect(result.current.visibleIds).toContain('custom-standard');
    expect(JSON.parse(storage._map[Object.keys(storage._map)[0]])).toContain('custom-standard');
    act(() => result.current.toggle('custom-standard'));
    expect(result.current.visibleIds).not.toContain('custom-standard');
  });

  it('initialises from the injected storage, not the real localStorage', () => {
    // readVisibleStandardIds(storage) is honored on writes; the initial
    // useState read must use the same injected storage rather than falling
    // through to the real, unrelated localStorage.
    window.localStorage.clear();
    const storage = fakeStorage({
      [VISIBLE_STANDARDS_STORAGE_KEY]: JSON.stringify(['custom-only']),
    });
    const { result } = renderHook(() => useVisibleStandards({ storage }), { wrapper: withQueryClient() });
    expect(result.current.visibleIds).toEqual(['custom-only']);
  });

  it('add is idempotent and remove is a no-op when absent', () => {
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage }), { wrapper: withQueryClient() });
    act(() => result.current.add('custom-standard'));
    const afterFirstAdd = result.current.visibleIds;
    act(() => result.current.add('custom-standard'));
    expect(result.current.visibleIds).toBe(afterFirstAdd);
    act(() => result.current.remove('does-not-exist'));
    expect(result.current.visibleIds).toBe(afterFirstAdd);
  });

  it('isVisible reflects the current set', () => {
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage }), { wrapper: withQueryClient() });
    expect(result.current.isVisible('custom-standard')).toBe(false);
    act(() => result.current.add('custom-standard'));
    expect(result.current.isVisible('custom-standard')).toBe(true);
  });

  it('isVisible compares mixed-case ids case-insensitively', () => {
    // The server normalizes stored ids to lowercase, but custom/imported
    // standard ids aren't charset-constrained (e.g. "OWASP-Top10"). A raw
    // comparison would read a visible standard as hidden here.
    const storage = fakeStorage({
      [VISIBLE_STANDARDS_STORAGE_KEY]: JSON.stringify(['owasp-top10']),
    });
    const { result } = renderHook(() => useVisibleStandards({ storage }), { wrapper: withQueryClient() });
    expect(result.current.isVisible('OWASP-Top10')).toBe(true);
  });

  it('write-throughs a toggle to the server', async () => {
    const put = vi.spyOn(api, 'putStandardsVisibility').mockResolvedValue({});
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage, projectId: 'p1' }), { wrapper: withQueryClient() });
    act(() => result.current.toggle('security'));
    await waitFor(() => expect(put).toHaveBeenCalledWith('p1', expect.any(Array)));
  });

  it('does not call the server when no project is selected', () => {
    const put = vi.spyOn(api, 'putStandardsVisibility');
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage, projectId: null }), { wrapper: withQueryClient() });
    act(() => result.current.toggle('security'));
    expect(put).not.toHaveBeenCalled();
  });

  it('does not break the session when the server write fails', async () => {
    const put = vi.spyOn(api, 'putStandardsVisibility').mockRejectedValue(new Error('offline'));
    const storage = fakeStorage();
    const { result } = renderHook(() => useVisibleStandards({ storage, projectId: 'p1' }), { wrapper: withQueryClient() });
    act(() => result.current.toggle('custom-standard'));
    await waitFor(() => expect(put).toHaveBeenCalled());
    expect(result.current.visibleIds).toContain('custom-standard');
  });
});
