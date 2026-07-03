import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { createAssistantSession, postAssistantMessage } from '../../api/assistant.js';
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
  const [isOpen, setIsOpen] = useState(false);
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
  const stream = useAssistantStream(sessionId, { onDone: () => setTurnActive(false) });

  // A fresh session (open, project/run switch) has no turn in flight.
  useEffect(() => { setTurnActive(false); }, [sessionId]);

  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === '`' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const setHeight = useCallback((px) => {
    const next = clampHeight(px);
    setHeightState(next);
    writeStoredHeight(next);
  }, []);

  const startSession = useCallback(async (ctx) => {
    const key = `${ctx?.provider}:${ctx?.model}:${ctx?.projectId}:${ctx?.runId}`;
    if (key === sessionCtxKey && sessionId) return;
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
    // Ignore a stale resolution: a newer startSession for a different context
    // has since been requested, so committing this (older) one would let the
    // last-resolving response win regardless of request order.
    if (latestKeyRef.current !== key) return;
    setLocalError(null);
    setUserTurns([]);
    setSessionCtxKey(key);
    setSessionId(created.sessionId);
    setSessionMeta({ provider: ctx?.provider ?? null, model: ctx?.model ?? null });
  }, [sessionCtxKey, sessionId]);

  const sendMessage = useCallback(async (text, uiState) => {
    if (!sessionId) return;
    setLocalError(null);
    setUserTurns((prev) => [...prev, { role: 'user', text, atIndex: stream.messages.length }]);
    setTurnActive(true);  // turn is now in flight until the stream's done/error
    try {
      await postAssistantMessage(sessionId, { text, uiState });
    } catch (err) {
      // The optimistic user turn stays in the transcript; surface the failure
      // so the user knows the message didn't reach the assistant.
      setLocalError(`Couldn't send message: ${err?.message || err}`);
      setTurnActive(false);
    }
  }, [sessionId, stream.messages.length]);

  const messages = useMemo(
    () => mergeMessages(userTurns, stream.messages),
    [userTurns, stream.messages],
  );

  const value = useMemo(() => ({
    isOpen, open, close, toggle,
    height, setHeight,
    messages, streaming: turnActive, error: localError || stream.error,
    sessionReady: sessionId != null,
    provider: sessionMeta.provider, model: sessionMeta.model,
    startSession, sendMessage,
  }), [isOpen, open, close, toggle, height, setHeight, messages, turnActive, stream.error, localError, sessionId, sessionMeta, startSession, sendMessage]);

  return (
    <AssistantDrawerContext.Provider value={value}>
      {children}
    </AssistantDrawerContext.Provider>
  );
}
