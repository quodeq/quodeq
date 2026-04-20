import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from 'xterm-addon-fit';
import 'xterm/css/xterm.css';
import './LiveTerminal.css';

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

    const es = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/logs/stream`);
    esRef.current = es;

    const onMessage = (ev) => {
      term.writeln(ev.data ?? '');
      setLineCount((n) => n + 1);
    };
    const onDone = () => { es.close(); };
    const onError = () => { /* EventSource auto-reconnects; no-op */ };
    es.addEventListener('message', onMessage);
    es.addEventListener('done', onDone);
    es.addEventListener('error', onError);

    const onResize = () => { try { fit.fit(); } catch { /* ignore */ } };
    window.addEventListener('resize', onResize);

    return () => {
      window.removeEventListener('resize', onResize);
      es.close();
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
