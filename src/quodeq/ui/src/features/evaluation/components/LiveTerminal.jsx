import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import './LiveTerminal.css';

// Muted foreground so placeholder lines don't shout.
const PLACEHOLDER_COLOR = '\x1b[38;5;246m';
const COLOR_RESET = '\x1b[0m';

function placeholderFor(status) {
  if (status === 404) return 'No terminal output captured for this run.';
  if (status === 410) return 'Run artifacts removed.';
  return `Log unavailable (HTTP ${status}).`;
}

export default function LiveTerminal({ jobId }) {
  const containerRef = useRef(null);
  const termRef = useRef(null);
  const esRef = useRef(null);
  const [open, setOpen] = useState(true);
  const [lineCount, setLineCount] = useState(0);

  useEffect(() => {
    if (!jobId || !containerRef.current) return;

    const term = new Terminal({
      convertEol: true,
      fontFamily: 'ui-monospace, Menlo, monospace',
      fontSize: 12,
      theme: { background: '#0d1117' },
      scrollback: 10000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();
    termRef.current = term;

    let cancelled = false;
    let es = null;

    const writePlaceholder = (text) => {
      term.writeln(`${PLACEHOLDER_COLOR}${text}${COLOR_RESET}`);
      setLineCount(1);
    };

    const openStream = () => {
      es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/logs/stream`);
      esRef.current = es;
      const onMessage = (ev) => {
        term.writeln(ev.data ?? '');
        setLineCount((n) => n + 1);
      };
      const onDone = () => { es.close(); };
      const onError = () => { /* EventSource auto-reconnects while the endpoint is live */ };
      es.addEventListener('message', onMessage);
      es.addEventListener('done', onDone);
      es.addEventListener('error', onError);
    };

    // Probe the plain endpoint first. The SSE endpoint would auto-reconnect
    // forever on 404 (pre-feature runs without run.log), so we short-circuit
    // and show a placeholder instead of opening EventSource.
    fetch(`/api/jobs/${encodeURIComponent(jobId)}/logs?since=0`)
      .then((resp) => {
        if (cancelled) return;
        if (resp.ok) {
          openStream();
          return;
        }
        writePlaceholder(placeholderFor(resp.status));
      })
      .catch((err) => {
        if (cancelled) return;
        writePlaceholder(`Log probe failed: ${err?.message ?? err}`);
      });

    const onResize = () => { try { fit.fit(); } catch { /* ignore */ } };
    window.addEventListener('resize', onResize);

    return () => {
      cancelled = true;
      window.removeEventListener('resize', onResize);
      if (es) es.close();
      term.dispose();
      termRef.current = null;
      esRef.current = null;
    };
  }, [jobId]);

  return (
    <div className="live-terminal">
      <button
        type="button"
        className="live-terminal__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        {open ? '▾' : '▸'} Terminal ({lineCount} lines)
      </button>
      <div
        ref={containerRef}
        className={`live-terminal__body ${open ? '' : 'live-terminal__body--collapsed'}`}
      />
    </div>
  );
}
