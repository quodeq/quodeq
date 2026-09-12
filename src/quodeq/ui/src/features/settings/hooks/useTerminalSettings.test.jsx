import { it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useTerminalSettings from './useTerminalSettings.js';

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

it('is enabled by default and setEnabled persists + syncs across instances', () => {
  const a = renderHook(() => useTerminalSettings());
  const b = renderHook(() => useTerminalSettings());
  expect(a.result.current.enabled).toBe(true);
  act(() => a.result.current.setEnabled(false));
  expect(a.result.current.enabled).toBe(false);
  expect(localStorage.getItem('cc-terminal-enabled')).toBe('false');
  expect(b.result.current.enabled).toBe(false);
});

it('an explicit opt-out sticks across new instances', () => {
  localStorage.setItem('cc-terminal-enabled', 'false');
  const { result } = renderHook(() => useTerminalSettings());
  expect(result.current.enabled).toBe(false);
});

it('falls back to the default (enabled) when storage.getItem throws during init', () => {
  // Marked-major finding: loadEnabled runs in a useState initializer and a
  // storage-event handler, so a throwing storage.getItem must not crash
  // either path; it should fall back to the enabled-by-default value.
  const throwingStorage = {
    getItem: () => { throw new DOMException('SecurityError'); },
    setItem: () => {},
  };
  const { result } = renderHook(() => useTerminalSettings({ storage: throwingStorage }));
  expect(result.current.enabled).toBe(true);
});

it('a storage-event re-read does not crash when getItem throws, and warns instead', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  let shouldThrow = false;
  const flakyStorage = {
    getItem: (key) => {
      if (shouldThrow) throw new DOMException('SecurityError');
      return localStorage.getItem(key);
    },
    setItem: (key, value) => localStorage.setItem(key, value),
  };
  const { result } = renderHook(() => useTerminalSettings({ storage: flakyStorage }));
  expect(result.current.enabled).toBe(true);

  shouldThrow = true;
  act(() => window.dispatchEvent(new Event('storage')));

  expect(result.current.enabled).toBe(true);
  expect(warn).toHaveBeenCalled();
  warn.mockRestore();
});
