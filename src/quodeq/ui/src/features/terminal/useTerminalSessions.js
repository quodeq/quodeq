import { useCallback, useEffect, useRef, useState } from 'react';
import { listTerminalSessions, createTerminalSession, killTerminalSession } from '../../api/terminal.js';

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
          setActiveId((prev) => (list.some((s) => s.id === prev) ? prev : (list[list.length - 1]?.id ?? null)));
        } catch { /* server unreachable: keep current tabs; sockets surface it */ }
        finally { reconcilingRef.current = null; }
      })();
    }
    return reconcilingRef.current;
  }, []);

  useEffect(() => {
    if (enabled) reconcile();
  }, [enabled, reconcile]);

  const openSession = useCallback(async () => {
    try {
      const created = await createTerminalSession();
      await reconcile();
      if (created?.id) setActiveId(created.id);
    } catch {
      // 409 at the cap (or a race): the server is the source of truth.
      await reconcile();
    }
  }, [reconcile]);

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
  }, [reconcile]);

  const selectSession = useCallback((id) => {
    setActiveId(id);
    // Lazy cwd refresh for the status bar; no polling.
    reconcile({ createIfEmpty: false });
  }, [reconcile]);

  return { sessions, activeId, max, openSession, closeSession, selectSession, reconcile };
}
