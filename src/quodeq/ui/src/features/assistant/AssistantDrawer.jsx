import React, { useCallback, useState } from 'react';
import { useAssistantDrawer } from './AssistantDrawerProvider.jsx';
import { MessageList } from './MessageList.jsx';

/**
 * Residual assistant content rendered inside the shared BottomDrawer host.
 * The shell (aside, drag-resize, header controls, isOpen gating) lives in
 * `features/drawer/BottomDrawer.jsx`; this component owns only the title
 * label, the scrollable conversation (MessageList), the error banner, and
 * the monospace prompt input.
 *
 * `uiState` is passed in as a prop (current app view context, e.g. active
 * tab) and forwarded verbatim to `sendMessage` on every send.
 */
export function AssistantPane({ uiState }) {
  const { provider, model, messages, streaming, error, sendMessage } = useAssistantDrawer();
  const [draft, setDraft] = useState('');

  const handleSend = useCallback(() => {
    const text = draft.trim();
    if (!text || streaming) return;
    sendMessage(text, uiState);
    setDraft('');
  }, [draft, streaming, sendMessage, uiState]);

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSend(); }
  }, [handleSend]);

  return (
    <>
      <div className="assistant-drawer-subtitle">✦ assistant · {provider}{model ? ` · ${model}` : ''}</div>
      <MessageList messages={messages} streaming={streaming} />
      {error && <div className="assistant-drawer-error" role="alert">{error}</div>}
      <div className="assistant-drawer-input-row">
        <textarea
          className="assistant-drawer-input"
          placeholder="Ask the assistant…"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          rows={1}
        />
      </div>
    </>
  );
}
