import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
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
  const [userTurns, setUserTurns] = useState([]);

  const stream = useAssistantStream(sessionId);

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
    const { sessionId: newSessionId } = await createAssistantSession(ctx);
    setUserTurns([]);
    setSessionCtxKey(key);
    setSessionId(newSessionId);
  }, [sessionCtxKey, sessionId]);

  const sendMessage = useCallback((text, uiState) => {
    if (!sessionId) return;
    setUserTurns((prev) => [...prev, { role: 'user', text, atIndex: stream.messages.length }]);
    postAssistantMessage(sessionId, { text, uiState });
  }, [sessionId, stream.messages.length]);

  const messages = useMemo(
    () => mergeMessages(userTurns, stream.messages),
    [userTurns, stream.messages],
  );

  const value = useMemo(() => ({
    isOpen, open, close, toggle,
    height, setHeight,
    messages, streaming: stream.streaming, error: stream.error,
    sessionReady: sessionId != null,
    startSession, sendMessage,
  }), [isOpen, open, close, toggle, height, setHeight, messages, stream.streaming, stream.error, sessionId, startSession, sendMessage]);

  return (
    <AssistantDrawerContext.Provider value={value}>
      {children}
    </AssistantDrawerContext.Provider>
  );
}
