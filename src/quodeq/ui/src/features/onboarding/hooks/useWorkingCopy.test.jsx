import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useWorkingCopy } from './useWorkingCopy.js';

const picks = vi.hoisted(() => ({ next: null }));
vi.mock('../../dashboard/hooks/useFolderPicker.jsx', () => ({
  useFolderPicker: () => ({ browseFolder: async () => picks.next, picker: null }),
}));

const KEY = 'quodeq.lastCloneRoot';
const URL = 'https://github.com/acme/billing.git';

describe('useWorkingCopy', () => {
  beforeEach(() => { localStorage.clear(); picks.next = null; });

  it('a saved bare ~ (the old clone step default) reads as untouched', () => {
    localStorage.setItem(KEY, '~');
    const { result } = renderHook(() => useWorkingCopy(URL));
    expect(result.current.path).toBe('~/quodeq/repos/billing');
    expect(result.current.changed).toBe(false);
    expect(result.current.cloneDest).toBeUndefined();
  });

  it('an empty saved root reads as untouched too', () => {
    localStorage.setItem(KEY, '');
    const { result } = renderHook(() => useWorkingCopy(URL));
    expect(result.current.changed).toBe(false);
  });

  it('a real saved root is used and sent', () => {
    localStorage.setItem(KEY, '/Volumes/work');
    const { result } = renderHook(() => useWorkingCopy(URL));
    expect(result.current.path).toBe('/Volumes/work/billing');
    expect(result.current.cloneDest).toBe('/Volumes/work');
  });

  it('a picked root is remembered', async () => {
    picks.next = '/srv/code';
    const { result } = renderHook(() => useWorkingCopy(URL));
    await act(async () => { await result.current.change(); });
    expect(result.current.cloneDest).toBe('/srv/code');
    expect(localStorage.getItem(KEY)).toBe('/srv/code');
  });
});
