import React, { useCallback, useEffect, useRef } from 'react';
import { useTerminalSessions } from './useTerminalSessions.js';
import { useTerminalPaneStatus } from './hooks/useTerminalPaneStatus.js';
import { TerminalTabStrip } from './components/TerminalTabStrip.jsx';
import TerminalSessionView from './TerminalSessionView.jsx';
import TerminalHeader from './TerminalHeader.jsx';
import { LockIcon } from '../../components/CopyButton.jsx';
import { t } from '../../strings/index.js';

/**
 * The terminal panel: header, session tab strip, one TerminalSessionView per
 * server-side session, and a status bar. Each session is its own shell with
 * its own history; inactive sessions are hidden (display:none), never
 * unmounted, so their buffers and PTY sockets survive tab switches. The
 * whole panel likewise stays mounted while backgrounded behind the assistant
 * panel — `active` only gates fitting/focus in the views.
 */
function TerminalStatusBar({ shell, sessions, activeSession }) {
  return (
    <div className="tty-statusbar">
      {shell && <span>{shell}</span>}
      {shell && <span className="tty-statusbar-sep" aria-hidden="true">·</span>}
      <span>{sessions.length === 1
        ? t('terminal.sessionsOne', { count: sessions.length })
        : t('terminal.sessionsMany', { count: sessions.length })}</span>
      <span className="tty-statusbar-sep" aria-hidden="true">·</span>
      {/* The gate only ever admits loopback clients (terminal/gate.py); a
          shell in a browser deserves a visible, if quiet, answer to "who
          else can reach this?". */}
      <span className="tty-statusbar-lock" title={t('terminal.localhostTitle')}>
        <LockIcon />
        {t('terminal.localhostOnly')}
      </span>
      <span className="tty-statusbar-spacer" />
      {activeSession?.cwd && <span className="tty-statusbar-cwd" title={activeSession.cwd}>{activeSession.cwd}</span>}
    </div>
  );
}

function TerminalSessionViews({ sessions, paneLive, active, activeId, onGone, registerApi }) {
  return (
    <div className="tty-views">
      {sessions.map((s) => (
        <TerminalSessionView key={s.id} sessionId={s.id} live={paneLive}
          active={active && s.id === activeId}
          onGone={onGone} registerApi={registerApi} />
      ))}
    </div>
  );
}

// "Restart terminal" (from Settings) killed EVERY session server-side; the
// stale views' sockets are about to report 'gone'. Reconcile immediately:
// stale tabs drop, a fresh session is created, new views mount clean.
function useTerminalRestartListener(reconcile) {
  useEffect(() => {
    const onRestart = () => reconcile();
    window.addEventListener('quodeq:terminal-restart', onRestart);
    return () => window.removeEventListener('quodeq:terminal-restart', onRestart);
  }, [reconcile]);
}

// Copy support: each view registers its copy source; the header copies from
// whichever session is frontmost.
function useCopySupport(activeId) {
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
  return { registerApi, handleCopy };
}

export default function TerminalPane({ active }) {
  const { reason, checked, shell } = useTerminalPaneStatus();

  const paneLive = checked && reason === null;
  const { sessions, activeId, max, openSession, closeSession, selectSession, reconcile } =
    useTerminalSessions({ enabled: paneLive });

  useTerminalRestartListener(reconcile);
  const { registerApi, handleCopy } = useCopySupport(activeId);

  const handleGone = useCallback(() => { reconcile(); }, [reconcile]);

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
        <TerminalTabStrip
          sessions={sessions} activeId={activeId} max={max}
          selectSession={selectSession} closeSession={closeSession} openSession={openSession}
        />
      )}
      <TerminalSessionViews sessions={sessions} paneLive={paneLive} active={active} activeId={activeId} onGone={handleGone} registerApi={registerApi} />
      <TerminalStatusBar shell={shell} sessions={sessions} activeSession={activeSession} />
    </div>
  );
}
