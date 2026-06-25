import { describe, it, expect, vi, afterEach } from 'vitest';
import { syncNativeTitlebar, rgbToHex } from './nativeTitlebar.js';

afterEach(() => { delete window.pywebview; });

describe('rgbToHex', () => {
  it('converts rgb() to #rrggbb', () => {
    expect(rgbToHex('rgb(10, 14, 20)')).toBe('#0a0e14');
  });
  it('handles rgba() and extra spacing', () => {
    expect(rgbToHex('rgba(240, 97, 46, 1)')).toBe('#f0612e');
  });
  it('returns null for junk', () => {
    expect(rgbToHex('not a color')).toBeNull();
  });
});

describe('syncNativeTitlebar', () => {
  it('sends mode + a color argument to the bridge', () => {
    const set_titlebar_theme = vi.fn();
    window.pywebview = { api: { set_titlebar_theme } };
    syncNativeTitlebar(true);
    expect(set_titlebar_theme).toHaveBeenCalledTimes(1);
    expect(set_titlebar_theme.mock.calls[0][0]).toBe('dark');
    // second arg is the resolved color (string) or null in jsdom
    expect(set_titlebar_theme.mock.calls[0].length).toBe(2);
  });

  it('no-ops without the bridge', () => {
    expect(() => syncNativeTitlebar(true)).not.toThrow();
  });

  it('no-ops when the method is missing', () => {
    window.pywebview = { api: {} };
    expect(() => syncNativeTitlebar(true)).not.toThrow();
  });
});
