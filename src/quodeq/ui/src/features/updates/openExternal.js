export function openExternal(url) {
  if (!url) return;
  // The URL originates from the remote update API (latest_url / download_url),
  // so it crosses a trust boundary. Only follow web schemes — refuse
  // unparseable input and javascript:/data:/file: smuggled by a hostile or
  // MITM'd response.
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    return;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return;
  const api = typeof window !== 'undefined' && window.pywebview && window.pywebview.api;
  if (api && typeof api.open_browser === 'function') {
    try { api.open_browser(url); return; } catch { /* fall through to window.open */ }
  }
  if (typeof window !== 'undefined') window.open(url, '_blank', 'noopener');
}
