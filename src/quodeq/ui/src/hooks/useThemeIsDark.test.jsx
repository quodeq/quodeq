import { describe, it, expect, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useThemeIsDark } from './useThemeIsDark.js';

// The hook resolves dark/light from the APPLIED html[data-theme] attribute
// (set by useAppSettings / initial paint), not from settings state, so it
// stays correct no matter which code path changed the theme.

afterEach(() => {
  document.documentElement.removeAttribute('data-theme');
});

describe('useThemeIsDark', () => {
  it('is dark when data-theme is dark', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(true);
  });

  it('is dark for family dark variants like ifrit-dark', () => {
    document.documentElement.setAttribute('data-theme', 'ifrit-dark');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(true);
  });

  it('is light when data-theme is light', () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(false);
  });

  it('is light for family light variants like galadriel-light', () => {
    document.documentElement.setAttribute('data-theme', 'galadriel-light');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(false);
  });

  it('falls back to the OS preference when no data-theme is set', () => {
    // vitest.setup.js stubs matchMedia with matches: false
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(false);
  });

  it('reacts when the applied theme changes', async () => {
    document.documentElement.setAttribute('data-theme', 'light');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(false);
    document.documentElement.setAttribute('data-theme', 'dark');
    await waitFor(() => expect(result.current).toBe(true));
  });

  it('falls back to the OS preference when the attribute is removed', async () => {
    document.documentElement.setAttribute('data-theme', 'ifrit-dark');
    const { result } = renderHook(() => useThemeIsDark());
    expect(result.current).toBe(true);
    document.documentElement.removeAttribute('data-theme');
    await waitFor(() => expect(result.current).toBe(false));
  });
});
