import { useEffect, useRef, useState, useCallback } from 'react';
import { terminalSocketUrl } from '../../api/terminal.js';

export function useTerminalSocket({ active, onData }) {
  const [status, setStatus] = useState('idle');
  const wsRef = useRef(null);
  const onDataRef = useRef(onData);
  onDataRef.current = onData;

  useEffect(() => {
    if (!active) return undefined;
    const ws = new WebSocket(terminalSocketUrl());
    wsRef.current = ws;
    setStatus('connecting');
    ws.onopen = () => setStatus('open');
    ws.onclose = () => { setStatus('closed'); if (wsRef.current === ws) wsRef.current = null; };
    ws.onmessage = (e) => {
      const s = typeof e.data === 'string' ? e.data : '';
      if (s[0] === '0') onDataRef.current?.(s.slice(1));
    };
    return () => { ws.onopen = ws.onmessage = ws.onclose = null; try { ws.close(); } catch { /* noop */ }
      if (wsRef.current === ws) wsRef.current = null; };
  }, [active]);

  const send = useCallback((data) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send('0' + data);
  }, []);

  const resize = useCallback((cols, rows) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send('1' + JSON.stringify({ resize: { cols, rows } }));
  }, []);

  return { status, send, resize };
}
