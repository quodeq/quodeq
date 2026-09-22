import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../api/ApiContext.jsx';
import { readString, writeString } from '../../adapters/storage.js';

// Closing the drawer unmounts the pane (and this hook), so the selected tab
// must survive outside React state or reopening always lands on the newest
// session. localStorage (not sessionStorage): the desktop shell can recreate
// the webview page, and a stale id is harmless — reconcile validates it
// against the server list and falls back.
const ACTIVE_SESSION_KEY = 'quodeq.terminal.activeSession';
// Client-side fallback session cap shown until the first list response
// reports the server's real limit.
const DEFAULT_SESSION_CAP = 6;

function readStoredActive() {
  return readString(ACTIVE_SESSION_KEY);
}

// The network round-trip: list, creating one session first when the list is
// empty and the caller asked for that. Throws when the server is unreachable.
async function fetchSessionList({ listTerminalSessions, createTerminalSession, createIfEmpty }) {
  let r = await listTerminalSessions();
  if (!(r.sessions || []).length && createIfEmpty) {
    await createTerminalSession().catch((err) => {
      console.warn('terminal: create-if-empty session failed, list may still be empty', err);
    });
    r = await listTerminalSessions();
  }
  return { list: r.sessions || [], max: r.max };
}

// Keep the current tab when it still exists; on a fresh mount (drawer
// reopened) restore the last selected tab if that session still exists, else
// fall back to the newest one.
function pickActiveId(list, prev) {
  if (list.some((s) => s.id === prev)) return prev;
  const stored = readStoredActive();
  if (list.some((s) => s.id === stored)) return stored;
  return list[list.length - 1]?.id ?? null;
}

function makeReconcile({ listTerminalSessions, createTerminalSession, setSessions, setMax, setActiveId, reconcilingRef }) {
  // Only the network round-trip is caught: a genuinely unreachable server
  // keeps the current tabs and lets sockets surface it. The state updates
  // run outside the try so a bug in the reconcile logic itself doesn't get
  // silently swallowed as "server unreachable".
  async function runReconcile(createIfEmpty) {
    let fetched;
    try {
      fetched = await fetchSessionList({ listTerminalSessions, createTerminalSession, createIfEmpty });
    } catch (err) {
      console.debug('terminal: reconcile list unreachable, keeping current tabs', err);
      return;
    }
    setSessions(fetched.list);
    if (fetched.max) setMax(fetched.max);
    setActiveId((prev) => pickActiveId(fetched.list, prev));
  }
  return function reconcile({ createIfEmpty = true } = {}) {
    if (!reconcilingRef.current) {
      reconcilingRef.current = (async () => {
        try { await runReconcile(createIfEmpty); } finally { reconcilingRef.current = null; }
      })();
    }
    return reconcilingRef.current;
  };
}

function makeOpenSession({ createTerminalSession, reconcile, setActiveId }) {
  return async () => {
    try {
      const created = await createTerminalSession();
      await reconcile();
      if (created?.id) setActiveId(created.id);
    } catch (err) {
      // 409 at the cap (or a race): the server is the source of truth.
      console.warn('[useTerminalSessions] create session failed:', err);
      await reconcile();
    }
  };
}

function makeCloseSession({ sessionsRef, setSessions, setActiveId, killTerminalSession, reconcile }) {
  return async (id) => {
    // Drop it locally FIRST: unmounting the view closes its socket and
    // disposes xterm before the server kill, so the socket never sees the
    // kill as an unexpected drop and starts reconnect backoff into a 4004.
    const prev = sessionsRef.current;
    const idx = prev.findIndex((s) => s.id === id);
    const next = prev.filter((s) => s.id !== id);
    const neighbor = (next[idx - 1] || next[0])?.id ?? null;
    setSessions(next);
    setActiveId((cur) => (cur === id ? neighbor : cur));
    // The tab is already gone from local state above, so a failed kill here
    // leaves an orphaned server-side session with no other trace: log it.
    await killTerminalSession(id).catch((err) => {
      console.warn('terminal: failed to kill session', id, err);
    });
    // Recreates a fresh session when the last tab was closed.
    await reconcile();
  };
}

function makeSelectSession({ setActiveId, reconcile }) {
  return (id) => {
    setActiveId(id);
    // Lazy cwd refresh for the status bar; no polling.
    reconcile({ createIfEmpty: false });
  };
}

/**
 * Client side of the session tab strip. The SERVER owns the canonical session
 * list (sessions survive page reloads and drawer closes); this hook reconciles
 * local state against it instead of persisting its own copy:
 *  - on mount: fetch the list, creating one session if it's empty (the panel
 *    never shows zero tabs);
 *  - on 'gone' sockets or a Settings restart (kill-all): refetch, drop stale
 *    ids, recreate one session if everything died;
 *  - on tab activation: refetch lazily so the status bar's cwd stays fresh
 *    without polling.
 * @param {{enabled: boolean}} args - `enabled` is false while the drawer is
 *   closed, which stops every fetch and socket this hook would otherwise open.
 */
export function useTerminalSessions({ enabled }) {
  const { listTerminalSessions, createTerminalSession, killTerminalSession } = useApi();
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [max, setMax] = useState(DEFAULT_SESSION_CAP);
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;
  // Serialize reconciles: a burst (N sockets all reporting 'gone' after a
  // server restart) must not fan out into N concurrent create calls.
  const reconcilingRef = useRef(null);

  const reconcile = useCallback(
    makeReconcile({ listTerminalSessions, createTerminalSession, setSessions, setMax, setActiveId, reconcilingRef }),
    [listTerminalSessions, createTerminalSession],
  );

  useEffect(() => {
    if (enabled) reconcile();
  }, [enabled, reconcile]);

  // Persist every selection change (click, create, close-neighbor, restore)
  // so the next mount of this hook starts from the same tab.
  useEffect(() => {
    if (!activeId) return;
    writeString(ACTIVE_SESSION_KEY, activeId);
  }, [activeId]);

  const openSession = useCallback(makeOpenSession({ createTerminalSession, reconcile, setActiveId }), [reconcile, createTerminalSession]);

  const closeSession = useCallback(
    makeCloseSession({ sessionsRef, setSessions, setActiveId, killTerminalSession, reconcile }),
    [reconcile, killTerminalSession],
  );

  const selectSession = useCallback(makeSelectSession({ setActiveId, reconcile }), [reconcile]);

  return { sessions, activeId, max, openSession, closeSession, selectSession, reconcile };
}
