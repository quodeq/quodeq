let since = -1;
const el = document.getElementById('logs');
async function poll() {
  try {
    const url = '/api/logs' + (since >= 0 ? '?since=' + since : '');
    const r = await fetch(url);
    if (!r.ok) return;
    const data = await r.json();
    if (data.lines.length) {
      const frag = document.createDocumentFragment();
      data.lines.forEach(e => {
        const line = document.createElement('div');
        const ts = e.timestamp ? e.timestamp.slice(11, 19) : '';
        const ets = ts.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        line.innerHTML = '<span class="ts">[' + ets + ']</span> ' +
          e.line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        frag.appendChild(line);
        since = e.index;
      });
      el.appendChild(frag);
      window.scrollTo(0, document.body.scrollHeight);
    }
  } catch (e) { console.warn('poll error', e); }
}
poll();
setInterval(poll, {{POLL_INTERVAL_MS}});
