/**
 * Assistant session lifecycle: create/reset sessions (with the latest-wins
 * race guard), the in-flight turn, per-conversation web/write toggles, the
 * repo/workspace mirror, and the merge-ready pieces (userTurns + the
 * underlying event stream) the provider combines into `messages` via
 * mergeMessages (in AssistantDrawerProvider.jsx).
 *
 * Composes hooks/useSessionLifecycle.js (session create/reset, the
 * latest-wins race guard, web/write toggles, repo/workspace mirror, the
 * stream) with hooks/useSessionActions.js (sendMessage/stopTurn/
 * addLocalExchange). The lifecycle's state setters feed the actions and are
 * not exposed.
 */
import { useSessionLifecycle, sessionKey } from './hooks/useSessionLifecycle.js';
import { useSessionActions } from './hooks/useSessionActions.js';

export { sessionKey };

export function useAssistantSession() {
  const { setUserTurns, setTurnActive, setLocalError, ...session } = useSessionLifecycle();
  const { sessionId, turnActive, stream, webEnabled, writeEnabled } = session;

  const actions = useSessionActions({
    sessionId, turnActive, stream, webEnabled, writeEnabled, setUserTurns, setTurnActive, setLocalError,
  });

  return { ...session, ...actions };
}
