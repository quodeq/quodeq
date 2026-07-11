import { it, expect, beforeEach, afterEach } from 'vitest';
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
