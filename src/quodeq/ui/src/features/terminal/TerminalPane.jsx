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

// True when the element isn't laid out (display:none / zero-size). Fitting xterm
// to a hidden box measures a 0x0 cell and drives the PTY to a bogus size, so the
// shell floods the prompt with cursor-position queries ("14;3R…"). Every fit
// path guards on this.
function isHidden(el) {
  return !el || el.offsetParent === null || el.clientWidth === 0 || el.clientHeight === 0;
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

  // The socket + xterm live as long as the terminal PANEL is open — NOT only
  // while it's the frontmost tab. Gating this on `active` would dispose the
  // terminal and drop the PTY socket on every tab switch (a backgrounded pane
  // is display:none, never unmounted), losing scrollback and the running shell.
  // `active` is used ONLY to gate fitting (the fit effects below).
  const paneLive = checked && reason === null;

  const { status, send, resize, reconnectNow } = useTerminalSocket({
    active: paneLive,
    restartKey,
    onData: (s) => termRef.current?.write(s),
    // Reset the screen on every (re)connect before the server replays
    // scrollback, so a reconnect to a still-alive backend repaints history
    // instead of appending a duplicate copy under it. Also re-enable input
    // (it's disabled while disconnected — see the status effect below).
    onOpen: () => {
      const term = termRef.current;
      if (!term) return;
      try { term.reset(); } catch { /* noop */ }
      term.options.disableStdin = false;
    },
  });

  // The size must reach the PTY only once the socket is OPEN. The resize sent
  // during mount is dropped (socket still connecting), which would leave the
  // PTY at the backend's default 80x24 while xterm renders the real (smaller)
  // drawer size — so full-screen TUIs like `claude`/`vim` draw off-screen and
  // look clipped. Re-fit and re-sync when the socket opens (and on reconnect).
  useEffect(() => {
    const el = rootRef.current;
    if (status !== 'open' || !fitRef.current || !termRef.current || isHidden(el)) return;
    try {
      fitRef.current.fit();
      resize(termRef.current.cols, termRef.current.rows);
    } catch { /* noop */ }
  }, [status, resize]);

  // Mount xterm once the terminal panel is live (open + enabled). It stays
  // mounted across tab switches (the pane is only hidden, never unmounted).
  useEffect(() => {
    if (!paneLive || termRef.current || !rootRef.current) return undefined;
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
      termRef.current = term; fitRef.current = fit;
      // Fit only when visible. If the pane mounts on a hidden/background tab,
      // fitting measures a 0x0 box (bogus PTY size); the status-open and
      // tab-activation effects both fit once the pane is actually shown.
      if (!isHidden(rootRef.current)) {
        try { fit.fit(); resize(term.cols, term.rows); } catch { /* noop */ }
      }
      // Debounce refits: during the sidebar-expand transition (and manual drag)
      // the container resizes every frame; refitting each frame thrashes xterm
      // and SIGWINCHes the PTY ~12x, so a running TUI redraws repeatedly and
      // "scratches". Fit ONCE after the size settles. (ResizeObserver isn't in
      // JSDOM; guard so tests and any lacking environment don't crash.)
      const scheduleFit = () => {
        if (fitTimer) clearTimeout(fitTimer);
        fitTimer = setTimeout(() => {
          fitTimer = null;
          // Never fit/resize while hidden (inactive tab / closed drawer): see
          // isHidden — a 0x0 fit drives the PTY to a bogus size and the shell
          // floods the prompt with cursor-position replies (the "14;3R…" garbage).
          if (isHidden(rootRef.current)) return;
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
  }, [paneLive, send, resize]);

  // Refit + re-sync the PTY when the tab becomes active again (it was hidden,
  // where we deliberately skip fitting). Guard on visibility so a stray call
  // while still hidden can't resize to 0.
  useEffect(() => {
    const el = rootRef.current;
    if (!active || !fitRef.current || !termRef.current || isHidden(el)) return;
    try { fitRef.current.fit(); resize(termRef.current.cols, termRef.current.rows); } catch { /* noop */ }
  }, [active, resize]);

  // Give xterm keyboard focus when the terminal becomes the frontmost tab
  // (drawer open or tab switch) so the user can type immediately without
  // clicking into it. Gated on `active` so a backgrounded pane never steals
  // focus; `paneLive` is a dep so this runs once the terminal has mounted on
  // first open (termRef is set by the mount effect declared above). No
  // isHidden guard: focus() doesn't resize the PTY, and an active tab is
  // visible by definition.
  useEffect(() => {
    if (!active || !paneLive || !termRef.current) return;
    try { termRef.current.focus(); } catch { /* noop */ }
  }, [active, paneLive]);

  // While the socket is not open, disable xterm input. send() already no-ops
  // when disconnected, so keystrokes would otherwise vanish silently into a
  // dead shell (and buffering them is unsafe — the line would land in a fresh
  // shell on reconnect). disableStdin makes xterm ignore input while the
  // "disconnected" overlay explains why. Declared after the mount effect so
  // termRef is set when this first runs. `paneLive` is a dep so it re-runs
  // once the terminal has mounted.
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    term.options.disableStdin = status !== 'open';
  }, [status, paneLive]);

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
  // A dead socket swallows keystrokes with no visual cue, so any not-connected
  // state after mount gets an explicit banner. 'connecting' is excluded: the
  // initial handshake resolves in milliseconds and a flash would be noise.
  const overlay = {
    reconnecting: { text: 'Terminal disconnected. Reconnecting…', btn: 'Retry now' },
    // Only one window may hold the single PTY. There is no takeover, so the
    // button offers an honest Retry (which succeeds once the other window is
    // closed) rather than a "Use it here" that silently does nothing.
    busy: { text: 'Terminal is open in another window. Close it there, then retry.', btn: 'Retry' },
    refused: { text: 'Terminal connection refused by the server.', btn: 'Retry' },
  }[status];
  return (
    <div className="tty-wrap" onKeyDown={containerKeyDown}>
      <div ref={rootRef} className="tty-root" data-testid="tty-root" />
      {overlay && (
        <div className="tty-overlay" data-testid="tty-overlay" role="status">
          <span>{overlay.text}</span>
          <button type="button" className="tty-overlay-btn" onClick={reconnectNow}>{overlay.btn}</button>
        </div>
      )}
    </div>
  );
}
