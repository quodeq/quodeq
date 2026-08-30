import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../api/ApiContext.jsx';
import { readString, writeString } from '../../adapters/storage.js';

// Closing the drawer unmounts the pane (and this hook), so the selected tab
// must survive outside React state or reopening always lands on the newest
// session. localStorage (not sessionStorage): the desktop shell can recreate
// the webview page, and a stale id is harmless — reconcile validates it
// against the server list and falls back.
const ACTIVE_SESSION_KEY = 'quodeq.terminal.activeSession';

function readStoredActive() {
  return readString(ACTIVE_SESSION_KEY);
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
 */
export function useTerminalSessions({ enabled }) {
  const { listTerminalSessions, createTerminalSession, killTerminalSession } = useApi();
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [max, setMax] = useState(6);
  const sessionsRef = useRef(sessions);
  sessionsRef.current = sessions;
  // Serialize reconciles: a burst (N sockets all reporting 'gone' after a
  // server restart) must not fan out into N concurrent create calls.
  const reconcilingRef = useRef(null);

  const reconcile = useCallback(({ createIfEmpty = true } = {}) => {
    if (!reconcilingRef.current) {
      reconcilingRef.current = (async () => {
        try {
          let r = await listTerminalSessions();
          if (!(r.sessions || []).length && createIfEmpty) {
            await createTerminalSession().catch(() => {});
            r = await listTerminalSessions();
          }
          const list = r.sessions || [];
          setSessions(list);
          if (r.max) setMax(r.max);
          setActiveId((prev) => {
            if (list.some((s) => s.id === prev)) return prev;
            // Fresh mount (drawer reopened): restore the last selected tab if
            // that session still exists, else fall back to the newest one.
            const stored = readStoredActive();
            if (list.some((s) => s.id === stored)) return stored;
            return list[list.length - 1]?.id ?? null;
          });
        } catch { /* server unreachable: keep current tabs; sockets surface it */ }
        finally { reconcilingRef.current = null; }
      })();
    }
    return reconcilingRef.current;
  }, [listTerminalSessions, createTerminalSession]);

  useEffect(() => {
    if (enabled) reconcile();
  }, [enabled, reconcile]);

  // Persist every selection change (click, create, close-neighbor, restore)
  // so the next mount of this hook starts from the same tab.
  useEffect(() => {
    if (!activeId) return;
    writeString(ACTIVE_SESSION_KEY, activeId);
  }, [activeId]);

  const openSession = useCallback(async () => {
    try {
      const created = await createTerminalSession();
      await reconcile();
      if (created?.id) setActiveId(created.id);
    } catch {
      // 409 at the cap (or a race): the server is the source of truth.
      await reconcile();
    }
  }, [reconcile, createTerminalSession]);

  const closeSession = useCallback(async (id) => {
    // Drop it locally FIRST: unmounting the view closes its socket and
    // disposes xterm before the server kill, so the socket never sees the
    // kill as an unexpected drop and starts reconnect backoff into a 4004.
    const prev = sessionsRef.current;
    const idx = prev.findIndex((s) => s.id === id);
    const next = prev.filter((s) => s.id !== id);
    const neighbor = (next[idx - 1] || next[0])?.id ?? null;
    setSessions(next);
    setActiveId((cur) => (cur === id ? neighbor : cur));
    await killTerminalSession(id).catch(() => {});
    // Recreates a fresh session when the last tab was closed.
    await reconcile();
  }, [reconcile, killTerminalSession]);

  const selectSession = useCallback((id) => {
    setActiveId(id);
    // Lazy cwd refresh for the status bar; no polling.
    reconcile({ createIfEmpty: false });
  }, [reconcile]);

  return { sessions, activeId, max, openSession, closeSession, selectSession, reconcile };
}
