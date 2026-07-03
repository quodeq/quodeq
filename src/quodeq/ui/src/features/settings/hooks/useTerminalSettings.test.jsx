import { it, expect, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useTerminalSettings from './useTerminalSettings.js';

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

it('is disabled by default and setEnabled persists + syncs across instances', () => {
  const a = renderHook(() => useTerminalSettings());
  const b = renderHook(() => useTerminalSettings());
  expect(a.result.current.enabled).toBe(false);
  act(() => a.result.current.setEnabled(true));
  expect(a.result.current.enabled).toBe(true);
  expect(localStorage.getItem('cc-terminal-enabled')).toBe('true');
  expect(b.result.current.enabled).toBe(true);
});
