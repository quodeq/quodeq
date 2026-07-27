import React, { useCallback, useEffect, useRef, useState } from 'react';
import { terminalStatus } from '../../api/terminal.js';
import { useTerminalSessions } from './useTerminalSessions.js';
import TerminalSessionView from './TerminalSessionView.jsx';
import TerminalHeader from './TerminalHeader.jsx';
import { LockIcon, PlusIcon, XIcon } from '../../components/CopyButton.jsx';

/**
 * The terminal panel: header, session tab strip, one TerminalSessionView per
 * server-side session, and a status bar. Each session is its own shell with
 * its own history; inactive sessions are hidden (display:none), never
 * unmounted, so their buffers and PTY sockets survive tab switches. The
 * whole panel likewise stays mounted while backgrounded behind the assistant
 * panel — `active` only gates fitting/focus in the views.
 */
export default function TerminalPane({ active }) {
  const [reason, setReason] = useState(null);
  const [checked, setChecked] = useState(false);
  const [shell, setShell] = useState('');

  useEffect(() => {
    let alive = true;
    terminalStatus().then((s) => {
      if (!alive) return;
      setReason(s.enabled ? null : s.reason);
      setShell(s.shell || '');
      setChecked(true);
    }).catch(() => { if (alive) { setReason('Terminal unavailable'); setChecked(true); } });
    return () => { alive = false; };
  }, []);

  const paneLive = checked && reason === null;
  const { sessions, activeId, max, openSession, closeSession, selectSession, reconcile } =
    useTerminalSessions({ enabled: paneLive });

  // "Restart terminal" (from Settings) killed EVERY session server-side; the
  // stale views' sockets are about to report 'gone'. Reconcile immediately:
  // stale tabs drop, a fresh session is created, new views mount clean.
  useEffect(() => {
    const onRestart = () => reconcile();
    window.addEventListener('quodeq:terminal-restart', onRestart);
    return () => window.removeEventListener('quodeq:terminal-restart', onRestart);
  }, [reconcile]);

  // Copy support: each view registers its copy source; the header copies from
  // whichever session is frontmost.
  const viewApis = useRef({});
  const registerApi = useCallback((id, api) => {
    if (api) viewApis.current[id] = api;
    else delete viewApis.current[id];
  }, []);
  const handleCopy = useCallback(() => {
    const text = viewApis.current[activeId]?.getCopyText() || '';
    if (!text) return false;
    navigator.clipboard?.writeText(text).catch(() => {});
    return true;
  }, [activeId]);

  const handleGone = useCallback(() => { reconcile(); }, [reconcile]);

  const onTabKeyDown = (e, id) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectSession(id); }
  };

  if (!checked) return null;
  if (reason) {
    return <div className="tty-disabled" data-testid="tty-disabled">{reason}</div>;
  }

  const activeSession = sessions.find((s) => s.id === activeId);
  // A lone session needs no tab strip — its "+" lives in the header instead;
  // the strip (with its own "+") appears once there are sessions to switch.
  const showTabs = sessions.length > 1;
  return (
    <div className="tty-shell">
      <TerminalHeader onCopy={handleCopy} onNewSession={showTabs ? null : openSession} />
      {showTabs && (
        <div className="tty-tabs" role="tablist" aria-label="Terminal sessions">
          {sessions.map((s) => (
            <div key={s.id} role="tab" aria-selected={s.id === activeId} tabIndex={0}
              className={`tty-tab${s.id === activeId ? ' tty-tab--active' : ''}`}
              onClick={() => selectSession(s.id)}
              onKeyDown={(e) => onTabKeyDown(e, s.id)}>
              <span className="tty-tab-dot" aria-hidden="true" />
              <span className="tty-tab-name">{s.name}</span>
              <button type="button" className="tty-tab-close"
                aria-label={`Close ${s.name}`} title="Close session"
                onClick={(e) => { e.stopPropagation(); closeSession(s.id); }}>
                <XIcon />
              </button>
            </div>
          ))}
          <button type="button" className="tty-tab-add" onClick={openSession}
            disabled={sessions.length >= max}
            aria-label="New session"
            title={sessions.length >= max ? `Limit of ${max} sessions reached` : 'New session'}>
            <PlusIcon />
          </button>
        </div>
      )}
      <div className="tty-views">
        {sessions.map((s) => (
          <TerminalSessionView key={s.id} sessionId={s.id} live={paneLive}
            active={active && s.id === activeId}
            onGone={handleGone} registerApi={registerApi} />
        ))}
      </div>
      <div className="tty-statusbar">
        {shell && <span>{shell}</span>}
        {shell && <span className="tty-statusbar-sep" aria-hidden="true">·</span>}
        <span>{sessions.length} session{sessions.length === 1 ? '' : 's'}</span>
        <span className="tty-statusbar-sep" aria-hidden="true">·</span>
        {/* The gate only ever admits loopback clients (terminal/gate.py); a
            shell in a browser deserves a visible, if quiet, answer to "who
            else can reach this?". */}
        <span className="tty-statusbar-lock" title="The embedded terminal only works on localhost">
          <LockIcon />
          localhost only
        </span>
        <span className="tty-statusbar-spacer" />
        {activeSession?.cwd && <span className="tty-statusbar-cwd" title={activeSession.cwd}>{activeSession.cwd}</span>}
      </div>
    </div>
  );
}
