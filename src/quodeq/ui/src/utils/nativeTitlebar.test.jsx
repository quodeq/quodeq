import { describe, it, expect, vi, afterEach } from 'vitest';
import { syncNativeTitlebar } from './nativeTitlebar.js';

afterEach(() => { delete window.pywebview; });

describe('syncNativeTitlebar', () => {
  it('calls set_titlebar_theme with dark/light', () => {
    const set_titlebar_theme = vi.fn();
    window.pywebview = { api: { set_titlebar_theme } };
    syncNativeTitlebar(true);
    expect(set_titlebar_theme).toHaveBeenCalledWith('dark');
    syncNativeTitlebar(false);
    expect(set_titlebar_theme).toHaveBeenCalledWith('light');
  });

  it('no-ops without the bridge', () => {
    expect(() => syncNativeTitlebar(true)).not.toThrow();
  });

  it('no-ops when the method is missing (browser/old bridge)', () => {
    window.pywebview = { api: {} };
    expect(() => syncNativeTitlebar(true)).not.toThrow();
  });
});
