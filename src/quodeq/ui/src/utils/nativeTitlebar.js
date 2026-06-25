/**
 * Mirror the app's effective dark/light theme to the native pywebview
 * titlebar. No-op in a browser (no window.pywebview) or before the bridge
 * finishes injecting (set_titlebar_theme missing).
 *
 * @param {boolean} dark - true when the app is rendering its dark theme
 */
export function syncNativeTitlebar(dark) {
  const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (!api || typeof api.set_titlebar_theme !== 'function') return;
  try {
    api.set_titlebar_theme(dark ? 'dark' : 'light');
  } catch {
    // bridge call failed — leave the titlebar at its current appearance
  }
}
