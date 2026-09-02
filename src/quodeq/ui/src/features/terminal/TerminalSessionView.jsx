import React, { useEffect, useRef, useCallback } from 'react';
import '@xterm/xterm/css/xterm.css';
import { useTerminalSocket } from './useTerminalSocket.js';
import { createTerminalInstance, isReservedChord } from './terminalSetup.js';
import { themeFromCss } from './xtermTheme.js';
import { t } from '../../strings/index.js';

// True when the element isn't laid out (display:none / zero-size). Fitting xterm
// to a hidden box measures a 0x0 cell and drives the PTY to a bogus size, so the
// shell floods the prompt with cursor-position queries ("14;3R…"). Every fit
// path guards on this. A display:none ANCESTOR (inactive session tab or
// backgrounded panel) also makes offsetParent null, so one guard covers both.
function isHidden(el) {
  return !el || el.offsetParent === null || el.clientWidth === 0 || el.clientHeight === 0;
}

/**
 * One shell session: an xterm instance bound to one server-side PTY over its
 * own WebSocket. Lives as long as the session exists — an inactive session
 * tab hides this view with display:none but never unmounts it, so the buffer
 * and socket survive tab switches (both between sessions and between the
 * drawer's panels). Unmounting is the disposal path when a session is closed.
 */
export default function TerminalSessionView({ sessionId, active, live, onGone, registerApi }) {
  const rootRef = useRef(null);
  const termRef = useRef(null);
  const fitRef = useRef(null);

  const { status, send, resize, reconnectNow } = useTerminalSocket({
    active: live,
    sessionId,
    onData: (s) => termRef.current?.write(s),
    // Reset the screen on every (re)connect before the server replays
    // scrollback, so a reconnect to a still-alive backend repaints history
    // instead of appending a duplicate copy under it. Also re-enable input
    // (it's disabled while disconnected — see the status effect below).
    onOpen: () => {
      const term = termRef.current;
      if (!term) return;
      try {
        term.reset();
        // One blank buffer row before the (re)played content: top breathing
        // room that scrolls away with the scrollback instead of being a fixed
        // viewport inset (which CSS padding on xterm would be).
        term.write('\r\n');
      } catch { /* noop */ }
      term.options.disableStdin = false;
    },
  });

  // The session evaporated server-side (server restart). Tell the owner so it
  // reconciles the tab strip against /terminal/sessions; retrying is futile.
  useEffect(() => {
    if (status === 'gone') onGone?.(sessionId);
  }, [status, sessionId, onGone]);

  // Expose the copy source to the header's Copy button: the selection when
  // there is one, else the visible viewport.
  useEffect(() => {
    if (!registerApi) return undefined;
    const getCopyText = () => {
      const term = termRef.current;
      if (!term) return '';
      const sel = term.getSelection?.();
      if (sel) return sel;
      const buf = term.buffer?.active;
      if (!buf) return '';
      const lines = [];
      for (let i = 0; i < term.rows; i += 1) {
        const line = buf.getLine(buf.viewportY + i);
        if (line) lines.push(line.translateToString(true));
      }
      return lines.join('\n').replace(/\n+$/, '');
    };
    registerApi(sessionId, { getCopyText });
    return () => registerApi(sessionId, null);
  }, [registerApi, sessionId]);

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

  // Mount xterm once the session is live. It stays mounted across tab
  // switches (the view is only hidden, never unmounted, while the session
  // exists).
  useEffect(() => {
    if (!live || termRef.current || !rootRef.current) return undefined;
    let disposed = false;
    let ro = null;
    let mo = null;
    let fitTimer = null;
    const linkProviders = [];

    const setup = () => {
      if (disposed || termRef.current || !rootRef.current) return;
      const { term, fit, linkProviders: providers } = createTerminalInstance({
        rootEl: rootRef.current, sessionId, send,
      });
      termRef.current = term; fitRef.current = fit;
      linkProviders.push(...providers);
      // Fit only when visible. If the view mounts hidden (background session
      // tab or backgrounded panel), fitting measures a 0x0 box (bogus PTY
      // size); the status-open and activation effects both fit once shown.
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
      linkProviders.forEach((d) => { try { d.dispose(); } catch { /* noop */ } });
      if (termRef.current) { termRef.current.dispose(); }
      termRef.current = null; fitRef.current = null;
    };
  }, [live, sessionId, send, resize]);

  // Refit + re-sync the PTY when this session becomes visible again (it was
  // hidden, where we deliberately skip fitting). Guard on visibility so a
  // stray call while still hidden can't resize to 0.
  useEffect(() => {
    const el = rootRef.current;
    if (!active || !fitRef.current || !termRef.current || isHidden(el)) return;
    try { fitRef.current.fit(); resize(termRef.current.cols, termRef.current.rows); } catch { /* noop */ }
  }, [active, resize]);

  // Give xterm keyboard focus when this session becomes the frontmost one so
  // the user can type immediately without clicking into it. Gated on `active`
  // so a backgrounded view never steals focus; `live` is a dep so this runs
  // once the terminal has mounted on first open. No isHidden guard: focus()
  // doesn't resize the PTY, and an active view is visible by definition.
  useEffect(() => {
    if (!active || !live || !termRef.current) return;
    try { termRef.current.focus(); } catch { /* noop */ }
  }, [active, live]);

  // While the socket is not open, disable xterm input. send() already no-ops
  // when disconnected, so keystrokes would otherwise vanish silently into a
  // dead shell (and buffering them is unsafe — the line would land in a fresh
  // shell on reconnect). disableStdin makes xterm ignore input while the
  // "disconnected" overlay explains why.
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    term.options.disableStdin = status !== 'open';
  }, [status, live]);

  // Bubble phase (NOT capture): xterm's textarea must receive the keydown
  // first so special keys (Delete/Backspace/arrows/Enter) work; we then stop
  // it bubbling to the window so the app's global handlers (Ctrl+[ history,
  // Escape closes the side pane) don't fire on terminal input. Reserved drawer
  // chords are left to bubble so Ctrl+` still toggles the drawer.
  const containerKeyDown = useCallback((e) => { if (!isReservedChord(e)) e.stopPropagation(); }, []);

  // A dead socket swallows keystrokes with no visual cue, so any not-connected
  // state after mount gets an explicit banner. 'connecting' is excluded: the
  // initial handshake resolves in milliseconds and a flash would be noise.
  // 'gone' is excluded too: the owner is already reconciling this view away.
  const overlay = {
    reconnecting: { text: t('terminal.disconnected'), btn: t('terminal.retryNow') },
    // Only one window may hold a session's PTY. There is no takeover, so the
    // button offers an honest Retry (which succeeds once the other window is
    // closed) rather than a "Use it here" that silently does nothing.
    busy: { text: t('terminal.openElsewhere'), btn: t('terminal.retry') },
    refused: { text: t('terminal.refused'), btn: t('terminal.retry') },
  }[status];

  return (
    <div className="tty-wrap" onKeyDown={containerKeyDown} style={{ display: active ? undefined : 'none' }}>
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
