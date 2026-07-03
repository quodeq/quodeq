import React, { useEffect, useRef, useState, useCallback } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { useTerminalSocket } from './useTerminalSocket.js';
import { terminalStatus } from '../../api/terminal.js';

// Two drawer chords are reserved for the host; return false so xterm lets them
// bubble to the window handler instead of typing into the shell.
function isReservedChord(e) {
  return e.code === 'Backquote' && (e.ctrlKey || e.metaKey);
}

function themeFromCss() {
  const s = getComputedStyle(document.documentElement);
  const v = (name, fb) => (s.getPropertyValue(name).trim() || fb);
  return {
    background: v('--color-surface-alt', '#1e1e1e'),
    foreground: v('--color-text', '#dcdcdc'),
    cursor: v('--color-accent', '#dcdcdc'),
  };
}

export default function TerminalPane({ active }) {
  const rootRef = useRef(null);
  const termRef = useRef(null);
  const fitRef = useRef(null);
  const [reason, setReason] = useState(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    terminalStatus().then((s) => { if (alive) { setReason(s.enabled ? null : s.reason); setChecked(true); } })
      .catch(() => { if (alive) { setReason('Terminal unavailable'); setChecked(true); } });
    return () => { alive = false; };
  }, []);

  const socketActive = active && checked && reason === null;

  const { status, send, resize } = useTerminalSocket({
    active: socketActive,
    onData: (s) => termRef.current?.write(s),
  });

  // The size must reach the PTY only once the socket is OPEN. The resize sent
  // during mount is dropped (socket still connecting), which would leave the
  // PTY at the backend's default 80x24 while xterm renders the real (smaller)
  // drawer size — so full-screen TUIs like `claude`/`vim` draw off-screen and
  // look clipped. Re-fit and re-sync when the socket opens (and on reconnect).
  useEffect(() => {
    if (status !== 'open' || !fitRef.current || !termRef.current) return;
    try {
      fitRef.current.fit();
      resize(termRef.current.cols, termRef.current.rows);
    } catch { /* noop */ }
  }, [status, resize]);

  // Mount xterm once when we're allowed and active.
  useEffect(() => {
    if (!socketActive || termRef.current || !rootRef.current) return undefined;
    // Same --font-mono family + 12px as the violations code panel, but a
    // tighter iTerm-like line height (1.6 read too airy for a terminal; the
    // xterm default 1.0 was too cramped).
    const term = new Terminal({
      scrollback: 5000,
      fontFamily: 'var(--font-mono, monospace)',
      fontSize: 12,
      lineHeight: 1.1,
      cursorBlink: true,
      cursorStyle: 'bar',     // sleeker than the default square block
      theme: themeFromCss(),
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(rootRef.current);
    term.attachCustomKeyEventHandler((e) => !isReservedChord(e));
    term.onData((d) => send(d));
    fit.fit();
    resize(term.cols, term.rows);
    termRef.current = term; fitRef.current = fit;
    // Not implemented in JSDOM; guard so tests (and any environment lacking it) don't crash.
    const ro = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(() => { try { fit.fit(); resize(term.cols, term.rows); } catch { /* noop */ } })
      : null;
    ro?.observe(rootRef.current);
    const onTheme = () => { term.options.theme = themeFromCss(); };
    const mo = typeof MutationObserver !== 'undefined' ? new MutationObserver(onTheme) : null;
    mo?.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => { ro?.disconnect(); mo?.disconnect(); term.dispose(); termRef.current = null; fitRef.current = null; };
  }, [socketActive, send, resize]);

  // Refit when the tab becomes active again (drawer was on the other tab).
  useEffect(() => { if (active && fitRef.current) { try { fitRef.current.fit(); } catch { /* noop */ } } }, [active]);

  // Bubble phase (NOT capture): xterm's textarea must receive the keydown
  // first so special keys (Delete/Backspace/arrows/Enter) work; we then stop
  // it bubbling to the window so the app's global handlers (Ctrl+[ history,
  // Escape closes the side pane) don't fire on terminal input. Reserved drawer
  // chords are left to bubble so Ctrl+` still toggles the drawer.
  const containerKeyDown = useCallback((e) => { if (!isReservedChord(e)) e.stopPropagation(); }, []);

  if (!checked) return null;
  if (reason) {
    return <div className="tty-disabled" data-testid="tty-disabled">{reason}</div>;
  }
  return <div ref={rootRef} className="tty-root" data-testid="tty-root" onKeyDown={containerKeyDown} />;
}
