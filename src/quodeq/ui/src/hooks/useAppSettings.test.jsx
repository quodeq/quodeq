import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAppSettings } from './useAppSettings.js';

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});
afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('useAppSettings', () => {
  it('defaults to system mode / daruma family when nothing is stored', () => {
    const { result } = renderHook(() => useAppSettings());
    expect(result.current.themeMode).toBe('system');
    expect(result.current.themeFamily).toBe('daruma');
  });

  it('applyMode persists the mode and updates state', () => {
    const { result } = renderHook(() => useAppSettings());
    act(() => result.current.applyMode('dark'));
    expect(result.current.themeMode).toBe('dark');
    expect(localStorage.getItem('cc-theme-mode')).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('applyFamily persists the family and updates state', () => {
    const { result } = renderHook(() => useAppSettings());
    act(() => result.current.applyFamily('ifrit'));
    expect(result.current.themeFamily).toBe('ifrit');
    expect(localStorage.getItem('cc-theme-family')).toBe('ifrit');
  });

  it('ignores an invalid mode value (no state change, no write)', () => {
    const { result } = renderHook(() => useAppSettings());
    act(() => result.current.applyMode('not-a-real-mode'));
    expect(result.current.themeMode).toBe('system');
    expect(localStorage.getItem('cc-theme-mode')).toBeNull();
  });

  it('ignores an invalid family value (no state change, no write)', () => {
    const { result } = renderHook(() => useAppSettings());
    act(() => result.current.applyFamily('not-a-real-family'));
    expect(result.current.themeFamily).toBe('daruma');
    expect(localStorage.getItem('cc-theme-family')).toBeNull();
  });

  // Behavior change (SANCTIONED, see PR description): applyMode/applyFamily
  // used to call storage.setItem directly, so a quota/private-mode throw
  // aborted the function before data-theme was ever applied. Routing through
  // the adapter's throw-tolerant writeString means the theme still applies
  // even when persistence fails.
  it('quota-throw during persistence does not abort theme application', () => {
    const { result } = renderHook(() => useAppSettings());
    const throwingStorage = {
      getItem: () => null,
      setItem: () => { throw new Error('quota exceeded'); },
      removeItem: () => {},
    };
    act(() => result.current.applyMode('dark', throwingStorage));
    expect(result.current.themeMode).toBe('dark');
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('runs the old-theme-key migration once on mount', () => {
    localStorage.setItem('cc-theme', 'ember');
    const { result } = renderHook(() => useAppSettings());
    expect(result.current.themeMode).toBe('dark');
    expect(result.current.themeFamily).toBe('ifrit');
    expect(localStorage.getItem('cc-theme')).toBeNull();
  });
});
