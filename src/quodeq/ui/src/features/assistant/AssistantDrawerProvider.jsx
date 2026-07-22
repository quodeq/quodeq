import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { createAssistantSession, fetchAssistantCatalog, fetchAssistantWorkspace, postAssistantMessage, stopAssistantTurn } from '../../api/assistant.js';
import useAssistantProvider from '../settings/hooks/useAssistantProvider.js';
import useTerminalSettings from '../settings/hooks/useTerminalSettings.js';
import { useAssistantStream } from './useAssistantStream.js';

const STORAGE_KEY = 'cc-assistant-drawer-height';
const DEFAULT_HEIGHT = 320;
const MIN_HEIGHT = 160;
const MAX_HEIGHT = 640;

function clampHeight(px) {
  return Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, px));
}

function readStoredHeight() {
  try {
    if (typeof localStorage === 'undefined') return DEFAULT_HEIGHT;
    const raw = localStorage.getItem(STORAGE_KEY);
    const n = raw ? parseInt(raw, 10) : NaN;
    return Number.isFinite(n) ? clampHeight(n) : DEFAULT_HEIGHT;
  } catch {
    return DEFAULT_HEIGHT;
  }
}

function writeStoredHeight(px) {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, String(px));
  } catch {
    /* quota / disabled — ignore */
  }
}

// Interleaves locally-appended user turns with the stream's messages in the
// order they actually happened: each user turn records how many stream
// messages existed at the moment it was sent, so it's re-inserted at that
// point on every render instead of always being appended at the end.
export function mergeMessages(userTurns, streamMessages) {
  const merged = [];
  let ui = 0;
  for (let i = 0; i <= streamMessages.length; i += 1) {
    while (ui < userTurns.length && userTurns[ui].atIndex === i) {
      merged.push(userTurns[ui]);
      ui += 1;
    }
    if (i < streamMessages.length) merged.push(streamMessages[i]);
  }
  return merged;
}

const AssistantDrawerContext = createContext(null);

export function useAssistantDrawer() {
  const ctx = useContext(AssistantDrawerContext);
  if (ctx === null) {
    throw new Error('useAssistantDrawer must be used inside an <AssistantDrawerProvider>');
  }
  return ctx;
}

export function AssistantDrawerProvider({ children }) {
  // Each panel has an independent open/selected state. `openPanels` is the set
  // of panels currently in the drawer (in selection order); the drawer is open
  // iff it's non-empty, shows a tab per open panel, and `activeTab` is the one
  // in front. The topbar launchers toggle a panel's membership; clicking a
  // title-bar tab just changes which open panel is active.
  const [openPanels, setOpenPanels] = useState([]);
  const [activeTab, setActiveTab] = useState('assistant');
  const activeTabRef = useRef('assistant');
  activeTabRef.current = activeTab;
  const isOpen = openPanels.length > 0;
  const [height, setHeightState] = useState(readStoredHeight);
  const [sessionId, setSessionId] = useState(null);
  const [sessionCtxKey, setSessionCtxKey] = useState(null);
  // Provider/model of the active session, surfaced so the drawer header can
  // label the conversation. Sourced from the ctx passed to startSession.
  const [sessionMeta, setSessionMeta] = useState({ provider: null, model: null });
  const [userTurns, setUserTurns] = useState([]);
  // Local error surface for failures the stream can't report: a rejected
  // session-start or message POST. Rendered by the drawer alongside (and
  // taking precedence over) the stream's own error frames.
  const [localError, setLocalError] = useState(null);
  // Command/skill catalog for the welcome panel, autocomplete, and
  // meta-commands. Fetched once per app session on first drawer open;
  // failures leave it null and the UI degrades to the built-in commands.
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    if (!isOpen || catalog !== null) return undefined;
    let cancelled = false;
    fetchAssistantCatalog()
      .then((c) => { if (!cancelled) setCatalog(c); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [isOpen, catalog]);

  // Per-conversation web access. Default OFF and reset on every context
  // switch: web access is opt-in per conversation, never sticky.
  const [webEnabled, setWebEnabled] = useState(false);
  const toggleWebEnabled = useCallback(() => setWebEnabled((prev) => !prev), []);

  // Per-conversation write access: default OFF, reset on every context switch,
  // mirrors the web toggle. repoInfo/workspace mirror the server's view.
  const [writeEnabled, setWriteEnabled] = useState(false);
  const toggleWriteEnabled = useCallback(() => setWriteEnabled((prev) => !prev), []);
  const writeEnabledRef = useRef(false);
  writeEnabledRef.current = writeEnabled;
  const [repoInfo, setRepoInfo] = useState(null);   // {attached, reason, writeAvailable}
  const [workspace, setWorkspace] = useState(null); // status route's `worktree` object
  // Whether the active session is read-only (source: 'shared'), from the
  // create-session response. Reset on every context switch via commitSession,
  // same as repoInfo — never sticky across sessions.
  const [readOnly, setReadOnly] = useState(false);

  // Tracks the most recently *requested* session context key, set
  // synchronously at startSession call time. Because startSession awaits a
  // network round-trip, a check-then-act guard on React state would let two
  // rapid context switches both create sessions and let the older-context
  // response win. We instead commit a resolved session only if its key is
  // still the latest requested one.
  const latestKeyRef = useRef(null);

  // Whether a turn is actually in flight (between sending a message and the
  // stream's terminal done/error frame). This — NOT the SSE connection state —
  // drives the drawer's loading indicator and input-disable. Merely opening a
  // session connects the event stream, which must not look like "loading".
  const [turnActive, setTurnActive] = useState(false);

  const sessionIdRef = useRef(null);
  sessionIdRef.current = sessionId;
  const refreshWorkspace = useCallback(async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    try {
      const ws = await fetchAssistantWorkspace(sid);
      if (sessionIdRef.current !== sid) return;   // context switched mid-flight
      setWorkspace(ws.worktree);
    } catch { /* advisory only */ }
  }, []);
  const stream = useAssistantStream(sessionId, { onDone: () => {
    setTurnActive(false);
    if (writeEnabledRef.current) refreshWorkspace();
  } });

  // A fresh session (open, project/run switch) has no turn in flight.
  useEffect(() => { setTurnActive(false); }, [sessionId]);

  const { enabled: assistantEnabled } = useAssistantProvider();
  const { enabled: terminalEnabled } = useTerminalSettings();

  // Activate a panel, opening it if it isn't already (in-drawer tab click /
  // programmatic). Keeps any other open panel selected.
  const openTab = useCallback((tab) => {
    setActiveTab(tab);
    setOpenPanels((prev) => (prev.includes(tab) ? prev : [...prev, tab]));
  }, []);
  // In-drawer title-bar tab click: just change which open panel is active.
  const selectTab = useCallback((tab) => setActiveTab(tab), []);
  // Topbar launcher / chord toggle: open+activate the panel; if it's already
  // the active one, pressing again removes it (closing that tab). Any other
  // open panel stays selected.
  const toggleTopbar = useCallback((tab) => {
    setOpenPanels((prev) => {
      if (!prev.includes(tab)) { setActiveTab(tab); return [...prev, tab]; }
      if (activeTabRef.current !== tab) { setActiveTab(tab); return prev; }
      const next = prev.filter((t) => t !== tab);
      if (next.length) setActiveTab(next[next.length - 1]);
      return next;
    });
  }, []);

  // Maximized = grow the drawer to (near) full height; toggling restores the
  // previous drag height. Ephemeral (not persisted); reset when the drawer closes.
  const [maximized, setMaximized] = useState(false);
  const toggleMaximized = useCallback(() => setMaximized((m) => !m), []);

  // Defense in depth: open() is exposed on the context value, so a future
  // caller besides the keydown handler below could invoke it directly.
  const open = useCallback(() => {
    setOpenPanels((prev) => (prev.length ? prev : [activeTabRef.current]));
  }, []);
  const close = useCallback(() => setOpenPanels([]), []);          // close ALL panels
  const toggle = useCallback(() => setOpenPanels((prev) => (prev.length ? [] : [activeTabRef.current])), []);
  // Close just the ACTIVE tab: if another panel is still open the drawer stays
  // open and switches to it; only the last one closing hides the drawer.
  const closeActiveTab = useCallback(() => {
    setOpenPanels((prev) => {
      const next = prev.filter((t) => t !== activeTabRef.current);
      if (next.length) setActiveTab(next[next.length - 1]);
      return next;
    });
  }, []);

  // Close one SPECIFIC panel, active or not, leaving any other open panel
  // alone. If it was the active one, fall back to the most recent remaining
  // panel, same rule as closeActiveTab.
  const closePanel = useCallback((tab) => {
    setOpenPanels((prev) => {
      if (!prev.includes(tab)) return prev;
      const next = prev.filter((t) => t !== tab);
      if (next.length && activeTabRef.current === tab) setActiveTab(next[next.length - 1]);
      return next;
    });
  }, []);

  // A closed drawer is never "maximized".
  useEffect(() => { if (openPanels.length === 0 && maximized) setMaximized(false); }, [openPanels.length, maximized]);

  // Drop any panel whose feature was disabled in Settings; keep the rest.
  useEffect(() => {
    setOpenPanels((prev) => {
      const next = prev.filter((t) => (t === 'assistant' ? assistantEnabled : terminalEnabled));
      return next.length === prev.length ? prev : next;
    });
  }, [assistantEnabled, terminalEnabled]);
  // If the active tab got closed/disabled, fall back to another open panel.
  useEffect(() => {
    if (openPanels.length && !openPanels.includes(activeTab)) {
      setActiveTab(openPanels[openPanels.length - 1]);
    }
  }, [openPanels, activeTab]);

  useEffect(() => {
    if (!assistantEnabled && !terminalEnabled) return undefined;
    const handleKeyDown = (e) => {
      if (e.code !== 'Backquote' || !(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      // Terminal shortcut (Ctrl+Shift+`) is always available, regardless of
      // project source.
      if (e.shiftKey) {
        if (terminalEnabled) toggleTopbar('terminal');
        return;
      }
      // Shared projects get read-only sessions server-side, so the shortcut
      // opens the drawer for any source.
      if (assistantEnabled) toggleTopbar('assistant');
      else if (terminalEnabled) toggleTopbar('terminal');
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [assistantEnabled, terminalEnabled, toggleTopbar]);

  const setHeight = useCallback((px) => {
    const next = clampHeight(px);
    setHeightState(next);
    writeStoredHeight(next);
  }, []);

  // The last committed session context, kept so resetConversation can mint a
  // fresh session for the SAME project/run/provider.
  const lastCtxRef = useRef(null);

  const commitSession = useCallback(async (ctx, key) => {
    // Record this as the latest requested context synchronously, before the
    // await, so a later call can invalidate this one's resolution.
    latestKeyRef.current = key;
    let created;
    try {
      created = await createAssistantSession(ctx);
    } catch (err) {
      // Only surface the failure if this is still the context the user wants;
      // a superseded stale request shouldn't clobber a newer session's UI.
      if (latestKeyRef.current === key) {
        setLocalError(`Couldn't start assistant session: ${err?.message || err}`);
      }
      return;
    }
    // Ignore a stale resolution: a newer request for a different context has
    // since been made, so committing this (older) one would let the
    // last-resolving response win regardless of request order.
    if (latestKeyRef.current !== key) return;
    setLocalError(null);
    setUserTurns([]);
    setWebEnabled(false);
    setWriteEnabled(false);
    setRepoInfo({ attached: !!created.repoAttached, reason: created.repoReason || null,
                  writeAvailable: !!created.writeAvailable });
    setReadOnly(!!created.readOnly);
    setWorkspace(null);
    setSessionCtxKey(key);
    setSessionId(created.sessionId);
    setSessionMeta({ provider: ctx?.provider ?? null, model: ctx?.model ?? null });
    lastCtxRef.current = ctx;
  }, []);

  const startSession = useCallback(async (ctx) => {
    const key = `${ctx?.provider}:${ctx?.model}:${ctx?.projectId}:${ctx?.runId}:${ctx?.source || 'local'}`;
    if (key === sessionCtxKey && sessionId) return;
    await commitSession(ctx, key);
  }, [sessionCtxKey, sessionId, commitSession]);

  // Fresh session for the SAME context: each turn replays only its own
  // session's messages server-side, so a new session id gives the model a
  // clean history and the stream hook an empty transcript. No-op while a
  // turn is in flight or before any session exists.
  const resetConversation = useCallback(async () => {
    const ctx = lastCtxRef.current;
    if (!ctx || turnActive) return;
    // Must match startSession's key format exactly: sessionCtxKey is shared
    // state between the two, and a mismatched format here would make a
    // subsequent startSession for the SAME context fail its dedupe check
    // (stale-format key !== freshly-computed key) and mint a spurious extra
    // session.
    const key = `${ctx?.provider}:${ctx?.model}:${ctx?.projectId}:${ctx?.runId}:${ctx?.source || 'local'}`;
    await commitSession(ctx, key);
  }, [turnActive, commitSession]);

  const sendMessage = useCallback(async (text, uiState) => {
    if (!sessionId) return;
    setLocalError(null);
    setUserTurns((prev) => [...prev, { role: 'user', text, atIndex: stream.messages.length }]);
    setTurnActive(true);  // turn is now in flight until the stream's done/error
    try {
      await postAssistantMessage(sessionId, { text, uiState, webEnabled, writeEnabled });
    } catch (err) {
      // The optimistic user turn stays in the transcript; surface the failure
      // so the user knows the message didn't reach the assistant.
      setLocalError(`Couldn't send message: ${err?.message || err}`);
      setTurnActive(false);
    }
  }, [sessionId, stream.messages.length, webEnabled, writeEnabled]);

  // Ask the server to cancel the in-flight turn. turnActive stays true until
  // the stream's terminal `stopped` frame arrives (server truth, same as
  // done/error), so the UI can't unlock before the turn thread actually ends.
  const stopTurn = useCallback(async () => {
    if (!sessionId || !turnActive) return;
    try {
      await stopAssistantTurn(sessionId);
    } catch (err) {
      setLocalError(`Couldn't stop the turn: ${err?.message || err}`);
    }
  }, [sessionId, turnActive]);

  // Client-answered meta-commands (/help, /skills, /actions): show the user
  // turn and the local response in the transcript without any server call.
  const addLocalExchange = useCallback((userText, responseText) => {
    setUserTurns((prev) => [...prev,
      { role: 'user', text: userText, atIndex: stream.messages.length },
      { role: 'local', text: responseText, atIndex: stream.messages.length },
    ]);
  }, [stream.messages.length]);

  const messages = useMemo(
    () => mergeMessages(userTurns, stream.messages),
    [userTurns, stream.messages],
  );

  const value = useMemo(() => ({
    isOpen, open, close, toggle, closeActiveTab, closePanel,
    openPanels, activeTab, openTab, selectTab, toggleTopbar, terminalEnabled,
    height, setHeight, maximized, toggleMaximized, setMaximized,
    messages, streaming: turnActive, error: localError || stream.error,
    sessionReady: sessionId != null,
    provider: sessionMeta.provider, model: sessionMeta.model,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled, repoInfo, readOnly, workspace, refreshWorkspace,
    sessionId,
    catalog, addLocalExchange,
    startSession, sendMessage, stopTurn, resetConversation,
  }), [isOpen, open, close, toggle, closeActiveTab, closePanel, openPanels, activeTab, openTab, selectTab, toggleTopbar, terminalEnabled, height, setHeight, maximized, toggleMaximized, messages, turnActive, stream.error, localError, sessionId, sessionMeta, webEnabled, toggleWebEnabled, writeEnabled, toggleWriteEnabled, repoInfo, readOnly, workspace, refreshWorkspace, catalog, addLocalExchange, startSession, sendMessage, stopTurn, resetConversation]);

  return (
    <AssistantDrawerContext.Provider value={value}>
      {children}
    </AssistantDrawerContext.Provider>
  );
}
