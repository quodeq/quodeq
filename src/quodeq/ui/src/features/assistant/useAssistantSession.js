/**
 * Assistant session lifecycle: create/reset sessions (with the latest-wins
 * race guard), the in-flight turn, per-conversation web/write toggles, the
 * repo/workspace mirror, and the merge-ready pieces (userTurns + the
 * underlying event stream) the provider combines into `messages` via
 * mergeMessages (kept in AssistantDrawerProvider.jsx, not moved here).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../api/ApiContext.jsx';
import { useAssistantStream } from './useAssistantStream.js';
import { t } from '../../strings/index.js';

/**
 * `provider:model:projectId:runId:source` — the identity of a session's
 * context. Two starts for the same context dedupe; a different context
 * (even the same project, different source) mints a distinct session.
 * Was duplicated verbatim at two call sites (startSession, resetConversation)
 * before this extraction.
 */
export function sessionKey(ctx) {
  return `${ctx?.provider}:${ctx?.model}:${ctx?.projectId}:${ctx?.runId}:${ctx?.source || 'local'}`;
}

export function useAssistantSession() {
  const { createAssistantSession, fetchAssistantWorkspace, postAssistantMessage, stopAssistantTurn } = useApi();
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
  }, [fetchAssistantWorkspace]);
  const stream = useAssistantStream(sessionId, { onDone: () => {
    setTurnActive(false);
    if (writeEnabledRef.current) refreshWorkspace();
  } });

  // A fresh session (open, project/run switch) has no turn in flight.
  useEffect(() => { setTurnActive(false); }, [sessionId]);

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
        setLocalError(t('assistant.startSessionFailed', { error: err?.message || err }));
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
  }, [createAssistantSession]);

  const startSession = useCallback(async (ctx) => {
    const key = sessionKey(ctx);
    // Re-claim the latest-requested key even when deduping: a superseded
    // in-flight commit for a DIFFERENT context must not land after the user
    // returned to this one (rapid source flip-flop race).
    latestKeyRef.current = key;
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
    // Must match startSession's key format exactly (sessionKey): sessionCtxKey
    // is shared state between the two, and a mismatched format here would
    // make a subsequent startSession for the SAME context fail its dedupe
    // check (stale-format key !== freshly-computed key) and mint a spurious
    // extra session.
    const key = sessionKey(ctx);
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
      setLocalError(t('assistant.sendFailed', { error: err?.message || err }));
      setTurnActive(false);
    }
  }, [sessionId, stream.messages.length, webEnabled, writeEnabled, postAssistantMessage]);

  // Ask the server to cancel the in-flight turn. turnActive stays true until
  // the stream's terminal `stopped` frame arrives (server truth, same as
  // done/error), so the UI can't unlock before the turn thread actually ends.
  const stopTurn = useCallback(async () => {
    if (!sessionId || !turnActive) return;
    try {
      await stopAssistantTurn(sessionId);
    } catch (err) {
      setLocalError(t('assistant.stopTurnFailed', { error: err?.message || err }));
    }
  }, [sessionId, turnActive, stopAssistantTurn]);

  // Client-answered meta-commands (/help, /skills, /actions): show the user
  // turn and the local response in the transcript without any server call.
  const addLocalExchange = useCallback((userText, responseText) => {
    setUserTurns((prev) => [...prev,
      { role: 'user', text: userText, atIndex: stream.messages.length },
      { role: 'local', text: responseText, atIndex: stream.messages.length },
    ]);
  }, [stream.messages.length]);

  return {
    sessionId, sessionMeta, userTurns, localError, stream, turnActive,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled,
    repoInfo, workspace, readOnly, refreshWorkspace,
    addLocalExchange, startSession, sendMessage, stopTurn, resetConversation,
  };
}
