/**
 * Assistant session lifecycle: create/reset sessions (with the latest-wins
 * race guard), the in-flight turn, per-conversation web/write toggles, the
 * repo/workspace mirror, and the merge-ready pieces (userTurns + the
 * underlying event stream) the provider combines into `messages` via
 * mergeMessages (kept in AssistantDrawerProvider.jsx, not moved here).
 *
 * Split into hooks/useSessionLifecycle.js (session create/reset, the
 * latest-wins race guard, web/write toggles, repo/workspace mirror, the
 * stream) and hooks/useSessionActions.js (sendMessage/stopTurn/
 * addLocalExchange) -- this file composes the two back into the same
 * return shape as before the split.
 */
import { useSessionLifecycle, sessionKey } from './hooks/useSessionLifecycle.js';
import { useSessionActions } from './hooks/useSessionActions.js';

export { sessionKey };

export function useAssistantSession() {
  const lifecycle = useSessionLifecycle();
  const {
    sessionId, sessionMeta, userTurns, setUserTurns, localError, setLocalError,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled,
    repoInfo, workspace, readOnly, refreshWorkspace,
    stream, turnActive, setTurnActive,
    startSession, resetConversation,
  } = lifecycle;

  const { sendMessage, stopTurn, addLocalExchange } = useSessionActions({
    sessionId, turnActive, stream, webEnabled, writeEnabled, setUserTurns, setTurnActive, setLocalError,
  });

  return {
    sessionId, sessionMeta, userTurns, localError, stream, turnActive,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled,
    repoInfo, workspace, readOnly, refreshWorkspace,
    addLocalExchange, startSession, sendMessage, stopTurn, resetConversation,
  };
}
