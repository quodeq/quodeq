/**
 * Mirror the app's effective theme to the native pywebview titlebar:
 * dark/light + the topbar's background color, so the macOS titlebar takes
 * the theme color. No-op in a browser or before the bridge injects.
 */

/** Parse "rgb(r, g, b)" / "rgba(...)" into "#rrggbb", or null. */
export function rgbToHex(rgb) {
  const m = String(rgb).match(/\d+(?:\.\d+)?/g);
  if (!m || m.length < 3) return null;
  const h = (n) => Math.round(Number(n)).toString(16).padStart(2, '0');
  return `#${h(m[0])}${h(m[1])}${h(m[2])}`;
}

/** Resolve a CSS custom property to a concrete #rrggbb via the cascade. */
export function resolveCssColorVar(varName) {
  if (typeof document === 'undefined' || !document.body) return null;
  const probe = document.createElement('span');
  probe.style.cssText = `display:none;color:var(${varName})`;
  document.body.appendChild(probe);
  const rgb = getComputedStyle(probe).color;
  probe.remove();
  return rgbToHex(rgb);
}

export function syncNativeTitlebar(dark) {
  const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (!api || typeof api.set_titlebar_theme !== 'function') return;
  try {
    const color = resolveCssColorVar('--color-surface');
    api.set_titlebar_theme(dark ? 'dark' : 'light', color || null);
  } catch {
    // bridge call failed — leave the titlebar at its current appearance
  }
}
