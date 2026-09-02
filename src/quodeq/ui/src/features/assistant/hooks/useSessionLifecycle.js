import { useCallback, useEffect, useRef, useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { useAssistantStream } from '../useAssistantStream.js';
import { t } from '../../../strings/index.js';

/**
 * Assistant session lifecycle: create/reset sessions (with the latest-wins
 * race guard, moved here whole), the per-conversation web/write toggles, the
 * repo/workspace mirror, and the stream itself. Extracted verbatim from
 * useAssistantSession.js; useSessionActions.js (sendMessage/stopTurn/
 * addLocalExchange) is the sibling half.
 *
 * sessionKey lives here (not useAssistantSession.js) purely to avoid a
 * circular import -- useAssistantSession.js re-exports it so its own import
 * surface (pinned by useAssistantSession.test.jsx) stays unchanged.
 */

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
// Groups useSessionLifecycle's own useState/useRef declarations so the outer
// hook's body stays under the function-length cap; still called
// unconditionally at the top of the outer hook, so hook-order is unaffected.
function useSessionCoreFields() {
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
  const sessionIdRef = useRef(null);
  sessionIdRef.current = sessionId;
  // The last committed session context, kept so resetConversation can mint a
  // fresh session for the SAME project/run/provider.
  const lastCtxRef = useRef(null);

  return {
    sessionId, setSessionId, sessionCtxKey, setSessionCtxKey, sessionMeta, setSessionMeta,
    userTurns, setUserTurns, localError, setLocalError, latestKeyRef, sessionIdRef, lastCtxRef,
  };
}

// Per-conversation web/write access toggles (default OFF, reset on every
// context switch — opt-in never sticky) plus the repo/workspace mirror of
// the server's view and the in-flight-turn flag.
function useSessionAccessFields() {
  const [webEnabled, setWebEnabled] = useState(false);
  const toggleWebEnabled = useCallback(() => setWebEnabled((prev) => !prev), []);

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
  // Whether a turn is actually in flight (between sending a message and the
  // stream's terminal done/error frame). This — NOT the SSE connection state —
  // drives the drawer's loading indicator and input-disable. Merely opening a
  // session connects the event stream, which must not look like "loading".
  const [turnActive, setTurnActive] = useState(false);

  return {
    webEnabled, setWebEnabled, toggleWebEnabled, writeEnabled, setWriteEnabled, toggleWriteEnabled, writeEnabledRef,
    repoInfo, setRepoInfo, workspace, setWorkspace, readOnly, setReadOnly, turnActive, setTurnActive,
  };
}

// commitSession resolves a session-create request and, if its key is still
// the latest requested one, commits the fresh session state. Extracted as a
// factory (called once, wrapped in useCallback below) purely to keep
// useSessionLifecycle's own body under the function-length cap.
function makeCommitSession({
  createAssistantSession, latestKeyRef, setLocalError, setUserTurns, setWebEnabled, setWriteEnabled,
  setRepoInfo, setReadOnly, setWorkspace, setSessionCtxKey, setSessionId, setSessionMeta, lastCtxRef,
}) {
  return async function commitSession(ctx, key) {
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
  };
}

function makeStartSession({ latestKeyRef, sessionCtxKey, sessionId, commitSession }) {
  return async (ctx) => {
    const key = sessionKey(ctx);
    // Re-claim the latest-requested key even when deduping: a superseded
    // in-flight commit for a DIFFERENT context must not land after the user
    // returned to this one (rapid source flip-flop race).
    latestKeyRef.current = key;
    if (key === sessionCtxKey && sessionId) return;
    await commitSession(ctx, key);
  };
}

// Fresh session for the SAME context: each turn replays only its own
// session's messages server-side, so a new session id gives the model a
// clean history and the stream hook an empty transcript. No-op while a
// turn is in flight or before any session exists.
function makeResetConversation({ lastCtxRef, turnActive, commitSession }) {
  return async () => {
    const ctx = lastCtxRef.current;
    if (!ctx || turnActive) return;
    // Must match startSession's key format exactly (sessionKey): sessionCtxKey
    // is shared state between the two, and a mismatched format here would
    // make a subsequent startSession for the SAME context fail its dedupe
    // check (stale-format key !== freshly-computed key) and mint a spurious
    // extra session.
    const key = sessionKey(ctx);
    await commitSession(ctx, key);
  };
}

function makeRefreshWorkspace({ sessionIdRef, fetchAssistantWorkspace, setWorkspace }) {
  return async () => {
    const sid = sessionIdRef.current;
    if (!sid) return;
    try {
      const ws = await fetchAssistantWorkspace(sid);
      if (sessionIdRef.current !== sid) return;   // context switched mid-flight
      setWorkspace(ws.worktree);
    } catch { /* advisory only */ }
  };
}

export function useSessionLifecycle() {
  const { createAssistantSession, fetchAssistantWorkspace } = useApi();
  const {
    sessionId, setSessionId, sessionCtxKey, setSessionCtxKey, sessionMeta, setSessionMeta,
    userTurns, setUserTurns, localError, setLocalError, latestKeyRef, sessionIdRef, lastCtxRef,
  } = useSessionCoreFields();
  const {
    webEnabled, setWebEnabled, toggleWebEnabled, writeEnabled, setWriteEnabled, toggleWriteEnabled, writeEnabledRef,
    repoInfo, setRepoInfo, workspace, setWorkspace, readOnly, setReadOnly, turnActive, setTurnActive,
  } = useSessionAccessFields();
  const refreshWorkspace = useCallback(
    makeRefreshWorkspace({ sessionIdRef, fetchAssistantWorkspace, setWorkspace }),
    [fetchAssistantWorkspace],
  );
  const stream = useAssistantStream(sessionId, { onDone: () => {
    setTurnActive(false);
    if (writeEnabledRef.current) refreshWorkspace();
  } });

  // A fresh session (open, project/run switch) has no turn in flight.
  useEffect(() => { setTurnActive(false); }, [sessionId]);

  const commitSession = useCallback(
    makeCommitSession({
      createAssistantSession, latestKeyRef, setLocalError, setUserTurns, setWebEnabled, setWriteEnabled,
      setRepoInfo, setReadOnly, setWorkspace, setSessionCtxKey, setSessionId, setSessionMeta, lastCtxRef,
    }),
    [createAssistantSession],
  );

  const startSession = useCallback(
    makeStartSession({ latestKeyRef, sessionCtxKey, sessionId, commitSession }),
    [sessionCtxKey, sessionId, commitSession],
  );

  const resetConversation = useCallback(
    makeResetConversation({ lastCtxRef, turnActive, commitSession }),
    [turnActive, commitSession],
  );

  return {
    sessionId, sessionMeta, userTurns, setUserTurns, localError, setLocalError,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled,
    repoInfo, workspace, readOnly, refreshWorkspace,
    stream, turnActive, setTurnActive,
    startSession, resetConversation,
  };
}
