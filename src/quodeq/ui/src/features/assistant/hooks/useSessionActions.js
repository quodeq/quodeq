import { useCallback } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { t } from '../../../strings/index.js';

/**
 * Assistant session actions: send a message, stop the in-flight turn, and
 * record a client-answered local exchange. Extracted verbatim from
 * useAssistantSession.js; useSessionLifecycle.js is the sibling half.
 */
export function useSessionActions({ sessionId, turnActive, stream, webEnabled, writeEnabled, setUserTurns, setTurnActive, setLocalError }) {
  const { postAssistantMessage, stopAssistantTurn } = useApi();

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

  return { sendMessage, stopTurn, addLocalExchange };
}
