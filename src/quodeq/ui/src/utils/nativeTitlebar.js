/**
 * Mirror the app's effective theme to the native pywebview titlebar:
 * dark/light + a titlebar color derived from the theme. The color is the
 * topbar surface tinted ~30% toward the theme accent — quodeq surfaces are
 * near-monochrome (white / near-black), so matching the surface alone reads
 * as a plain grey bar; the accent tint is what makes the frame visibly carry
 * the theme. No-op in a browser or before the bridge injects.
 */

const TITLEBAR_ACCENT_MIX = 0.3; // weight of the accent over the surface

/** Parse "rgb(r,g,b)" / "rgba(...)" into [r,g,b] (0-255), or null. */
function parseRgb(s) {
  const m = String(s).match(/\d+(?:\.\d+)?/g);
  if (!m || m.length < 3) return null;
  return m.slice(0, 3).map((n) => Math.round(Number(n)));
}

/** Accept "rgb(...)" or an [r,g,b] array; return "#rrggbb", or null. */
export function rgbToHex(rgb) {
  const a = Array.isArray(rgb) ? rgb : parseRgb(rgb);
  if (!a) return null;
  const h = (n) => Math.max(0, Math.min(255, n)).toString(16).padStart(2, '0');
  return `#${h(a[0])}${h(a[1])}${h(a[2])}`;
}

/** Resolve a CSS custom property to [r,g,b] via the cascade, or null. */
function resolveVarRgb(varName) {
  if (typeof document === 'undefined' || !document.body) return null;
  const probe = document.createElement('span');
  probe.style.cssText = `display:none;color:var(${varName})`;
  document.body.appendChild(probe);
  const rgb = parseRgb(getComputedStyle(probe).color);
  probe.remove();
  return rgb;
}

/** Titlebar color = surface tinted toward the accent, as "#rrggbb" (or null). */
export function resolveTitlebarColor() {
  const surface = resolveVarRgb('--color-surface');
  if (!surface) return null;
  const accent = resolveVarRgb('--color-accent');
  if (!accent) return rgbToHex(surface);
  const t = TITLEBAR_ACCENT_MIX;
  return rgbToHex(surface.map((s, i) => Math.round(accent[i] * t + s * (1 - t))));
}

export function syncNativeTitlebar(dark) {
  const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (!api || typeof api.set_titlebar_theme !== 'function') return;
  try {
    api.set_titlebar_theme(dark ? 'dark' : 'light', resolveTitlebarColor());
  } catch {
    // bridge call failed — leave the titlebar at its current appearance
  }
}
