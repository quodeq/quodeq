import { useEffect, useRef, useState, useCallback } from 'react';
import { terminalSocketUrl } from '../../api/terminal.js';

// App-specific WS close codes sent by the server (api/terminal_routes.py).
// They mean a reconnect cannot succeed right now, so the hook reports the
// state instead of retrying — a busy loop here would ping-pong against the
// server's single-connection lock and spam the other window's terminal.
const CLOSE_BUSY = 4002;     // another window holds the single PTY connection
const CLOSE_REFUSED = 4003;  // gate refused (non-loopback host / bad Origin)

const RETRY_BASE_MS = 500;
const RETRY_MAX_MS = 5000;

// status: 'idle' | 'connecting' | 'open' | 'reconnecting' | 'busy' | 'refused'
export function useTerminalSocket({ active, onData, onOpen, restartKey = 0 }) {
  const [status, setStatus] = useState('idle');
  // Bumped internally to open a fresh socket after an unexpected close.
  const [gen, setGen] = useState(0);
  const wsRef = useRef(null);
  const retryTimerRef = useRef(null);
  const attemptsRef = useRef(0);
  const onDataRef = useRef(onData);
  onDataRef.current = onData;
  // Fired on EVERY socket open (initial and reconnect), before the first
  // data frame, so the pane can reset xterm before the server replays
  // scrollback — otherwise a live-backend reconnect appends the whole
  // history under the existing buffer (prints twice on sleep/wake).
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;

  // An external restart (Settings kill -> fresh PTY) starts a fresh backoff
  // history; only an internal retry keeps counting attempts.
  useEffect(() => { attemptsRef.current = 0; }, [restartKey]);

  // `restartKey`/`gen` are dependencies so bumping either tears down the
  // current socket and opens a fresh one (restart from Settings / auto-retry).
  useEffect(() => {
    if (!active) return undefined;
    const ws = new WebSocket(terminalSocketUrl());
    wsRef.current = ws;
    setStatus(attemptsRef.current > 0 ? 'reconnecting' : 'connecting');
    ws.onopen = () => {
      attemptsRef.current = 0;
      // Runs before onmessage (WS delivers open before any frame), so the
      // reset lands ahead of the scrollback replay.
      onOpenRef.current?.();
      setStatus('open');
    };
    ws.onclose = (e) => {
      if (wsRef.current === ws) wsRef.current = null;
      if (e?.code === CLOSE_BUSY) { setStatus('busy'); return; }
      if (e?.code === CLOSE_REFUSED) { setStatus('refused'); return; }
      // Unexpected drop (server restart/crash/sleep). A dead socket swallows
      // keystrokes silently, so surface it and retry with capped exponential
      // backoff — the local server can come back at any moment.
      setStatus('reconnecting');
      const delay = Math.min(RETRY_BASE_MS * 2 ** attemptsRef.current, RETRY_MAX_MS);
      attemptsRef.current += 1;
      retryTimerRef.current = setTimeout(() => {
        retryTimerRef.current = null;
        setGen((g) => g + 1);
      }, delay);
    };
    ws.onmessage = (e) => {
      const s = typeof e.data === 'string' ? e.data : '';
      if (s[0] === '0') onDataRef.current?.(s.slice(1));
    };
    return () => {
      if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
      ws.onopen = ws.onmessage = ws.onclose = null;
      try { ws.close(); } catch { /* noop */ }
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [active, restartKey, gen]);

  const send = useCallback((data) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send('0' + data);
  }, []);

  const resize = useCallback((cols, rows) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send('1' + JSON.stringify({ resize: { cols, rows } }));
  }, []);

  // Manual retry (overlay click): skip any pending backoff and go now.
  const reconnectNow = useCallback(() => {
    if (retryTimerRef.current) { clearTimeout(retryTimerRef.current); retryTimerRef.current = null; }
    attemptsRef.current = 0;
    setGen((g) => g + 1);
  }, []);

  return { status, send, resize, reconnectNow };
}
