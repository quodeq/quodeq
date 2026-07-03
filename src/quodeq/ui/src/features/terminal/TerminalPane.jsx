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
  // Bumped to reconnect the socket after a restart (kill → fresh PTY).
  const [restartKey, setRestartKey] = useState(0);

  useEffect(() => {
    let alive = true;
    terminalStatus().then((s) => { if (alive) { setReason(s.enabled ? null : s.reason); setChecked(true); } })
      .catch(() => { if (alive) { setReason('Terminal unavailable'); setChecked(true); } });
    return () => { alive = false; };
  }, []);

  // "Restart terminal" (from Settings): clear the screen and reconnect. The
  // server session was already killed, so the reconnect spawns a fresh PTY.
  useEffect(() => {
    const onRestart = () => {
      try { termRef.current?.reset(); } catch { /* noop */ }
      setRestartKey((k) => k + 1);
    };
    window.addEventListener('quodeq:terminal-restart', onRestart);
    return () => window.removeEventListener('quodeq:terminal-restart', onRestart);
  }, []);

  const socketActive = active && checked && reason === null;

  const { status, send, resize } = useTerminalSocket({
    active: socketActive,
    restartKey,
    onData: (s) => termRef.current?.write(s),
  });

  // The size must reach the PTY only once the socket is OPEN. The resize sent
  // during mount is dropped (socket still connecting), which would leave the
  // PTY at the backend's default 80x24 while xterm renders the real (smaller)
  // drawer size — so full-screen TUIs like `claude`/`vim` draw off-screen and
  // look clipped. Re-fit and re-sync when the socket opens (and on reconnect).
  useEffect(() => {
    const el = rootRef.current;
    if (status !== 'open' || !fitRef.current || !termRef.current || !el || el.offsetParent === null) return;
    try {
      fitRef.current.fit();
      resize(termRef.current.cols, termRef.current.rows);
    } catch { /* noop */ }
  }, [status, resize]);

  // Mount xterm once when we're allowed and active.
  useEffect(() => {
    if (!socketActive || termRef.current || !rootRef.current) return undefined;
    let disposed = false;
    let ro = null;
    let mo = null;
    let fitTimer = null;

    const setup = () => {
      if (disposed || termRef.current || !rootRef.current) return;
      // A real terminal font (Menlo = macOS Terminal default, Monaco = iTerm's
      // classic default), NOT the code-panel's JetBrains Mono. All system fonts
      // — available synchronously, so xterm measures the cell correctly with no
      // webfont race (JBM, a Google webfont, caused the extra-spacing bug).
      const term = new Terminal({
        scrollback: 5000,
        fontFamily: 'Menlo, Monaco, "SF Mono", "SFMono-Regular", Consolas, "DejaVu Sans Mono", monospace',
        fontSize: 13,
        // iTerm-tight vertical rhythm. 1.5 read like a text editor (too airy);
        // iTerm's default is ~1.0 — 1.1 keeps a hair of breathing room.
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
      // Debounce refits: during the sidebar-expand transition (and manual drag)
      // the container resizes every frame; refitting each frame thrashes xterm
      // and SIGWINCHes the PTY ~12x, so a running TUI redraws repeatedly and
      // "scratches". Fit ONCE after the size settles. (ResizeObserver isn't in
      // JSDOM; guard so tests and any lacking environment don't crash.)
      const scheduleFit = () => {
        if (fitTimer) clearTimeout(fitTimer);
        fitTimer = setTimeout(() => {
          fitTimer = null;
          // Never fit/resize while hidden. On an inactive tab / closed drawer
          // the element is display:none (0x0); fitting to that drives the PTY
          // to a bogus size, and the shell then floods the prompt with
          // cursor-position query/replies (the "14;3R…" garbage).
          const el = rootRef.current;
          if (!el || el.offsetParent === null || el.clientWidth === 0 || el.clientHeight === 0) return;
          try { fit.fit(); resize(term.cols, term.rows); } catch { /* noop */ }
        }, 150);
      };
      ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(scheduleFit) : null;
      ro?.observe(rootRef.current);
      const onTheme = () => { term.options.theme = themeFromCss(); };
      mo = typeof MutationObserver !== 'undefined' ? new MutationObserver(onTheme) : null;
      mo?.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    };

    // System fonts are available synchronously, so there's no webfont-load race
    // to wait for — build immediately.
    setup();

    return () => {
      disposed = true;
      if (fitTimer) clearTimeout(fitTimer);
      ro?.disconnect(); mo?.disconnect();
      if (termRef.current) { termRef.current.dispose(); }
      termRef.current = null; fitRef.current = null;
    };
  }, [socketActive, send, resize]);

  // Refit + re-sync the PTY when the tab becomes active again (it was hidden,
  // where we deliberately skip fitting). Guard on visibility so a stray call
  // while still hidden can't resize to 0.
  useEffect(() => {
    const el = rootRef.current;
    if (!active || !fitRef.current || !termRef.current || !el || el.offsetParent === null) return;
    try { fitRef.current.fit(); resize(termRef.current.cols, termRef.current.rows); } catch { /* noop */ }
  }, [active, resize]);

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
