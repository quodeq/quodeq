const SINCE_UNSET = -1; // no line index seen yet: the first poll fetches everything
const MAX_LINES = 2000; // oldest lines are dropped past this so a tab left open for hours does not grow without bound
const LOGS_ENDPOINT = '/api/logs';
const SINCE_PARAM = 'since'; // query key: only lines after this index
const ISO_TIME_START = 11, ISO_TIME_END = 19; // the HH:MM:SS slice of an ISO timestamp
const STALLED_POLL_MSG = 'log stream unavailable, retrying'; // shown in #log-status until a poll succeeds again
let since = SINCE_UNSET;
const el = document.getElementById('logs');
const statusEl = document.getElementById('log-status');
function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function setStalled(stalled) {
  if (!statusEl) return;
  statusEl.textContent = stalled ? STALLED_POLL_MSG : '';
}
async function poll() {
  try {
    const url = LOGS_ENDPOINT + (since >= 0 ? '?' + SINCE_PARAM + '=' + since : '');
    const r = await fetch(url);
    if (!r.ok) { setStalled(true); return; }
    const data = await r.json();
    setStalled(false);
    if (data.lines.length) {
      const frag = document.createDocumentFragment();
      data.lines.forEach(e => {
        const line = document.createElement('div');
        const ts = e.timestamp ? e.timestamp.slice(ISO_TIME_START, ISO_TIME_END) : '';
        const lvl = e.level ? '<span class="lvl">' + escapeHtml(e.level) + '</span> ' : '';
        line.innerHTML = '<span class="ts">[' + escapeHtml(ts) + ']</span> ' + lvl +
          escapeHtml(e.line);
        frag.appendChild(line);
        since = e.index;
      });
      el.appendChild(frag);
      while (el.childElementCount > MAX_LINES) el.removeChild(el.firstElementChild);
      window.scrollTo(0, document.body.scrollHeight);
    }
  } catch (e) { console.warn('poll error', e); setStalled(true); }
}
poll();
setInterval(poll, {{POLL_INTERVAL_MS}});
