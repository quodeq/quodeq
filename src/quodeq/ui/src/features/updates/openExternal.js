export function openExternal(url) {
  if (!url) return;
  const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (api && typeof api.open_browser === 'function') {
    try { api.open_browser(url); return; } catch { /* fall through to window.open */ }
  }
  if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener');
}
