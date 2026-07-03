import React, { useCallback, useRef, useState } from 'react';
import { useAssistantDrawer } from './AssistantDrawerProvider.jsx';
import { MessageList } from './MessageList.jsx';

const MIN_DRAWER_HEIGHT = 160;

/**
 * Bottom, full-width "terminal" drawer for the LLM assistant. Renders
 * nothing when the drawer is closed; otherwise shows a header, the
 * scrollable conversation (MessageList), and a monospace prompt input.
 *
 * `uiState` is passed in as a prop (current app view context, e.g. active
 * tab) and forwarded verbatim to `sendMessage` on every send.
 */
export function AssistantDrawer({ uiState }) {
  const {
    isOpen, provider, model, height,
    messages, streaming, error,
    close, setHeight, sendMessage,
  } = useAssistantDrawer();

  const [draft, setDraft] = useState('');
  const dragRef = useRef(null);

  const handleDragMove = useCallback((event) => {
    if (!dragRef.current) return;
    const delta = dragRef.current.startY - event.clientY;
    setHeight(dragRef.current.startHeight + delta);
  }, [setHeight]);

  const handleDragEnd = useCallback(() => {
    dragRef.current = null;
    window.removeEventListener('pointermove', handleDragMove);
    window.removeEventListener('pointerup', handleDragEnd);
  }, [handleDragMove]);

  const handleDragStart = useCallback((event) => {
    dragRef.current = { startY: event.clientY, startHeight: height };
    window.addEventListener('pointermove', handleDragMove);
    window.addEventListener('pointerup', handleDragEnd);
  }, [height, handleDragMove, handleDragEnd]);

  const handleMinimize = useCallback(() => {
    setHeight(MIN_DRAWER_HEIGHT);
  }, [setHeight]);

  const handleSend = useCallback(() => {
    const text = draft.trim();
    if (!text || streaming) return;
    sendMessage(text, uiState);
    setDraft('');
  }, [draft, streaming, sendMessage, uiState]);

  const handleKeyDown = useCallback((event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  if (!isOpen) return null;

  return (
    <aside className="assistant-drawer" style={{ height }}>
      <div
        className="assistant-drawer-drag"
        onPointerDown={handleDragStart}
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize assistant drawer"
      />
      <header className="assistant-drawer-header">
        <span className="assistant-drawer-title">
          ✦ assistant · {provider}{model ? ` · ${model}` : ''}
        </span>
        <div className="assistant-drawer-controls">
          <button
            type="button"
            className="assistant-drawer-btn assistant-drawer-minimize"
            onClick={handleMinimize}
            aria-label="Minimize assistant"
            title="Minimize"
          >
            &#95;
          </button>
          <button
            type="button"
            className="assistant-drawer-btn assistant-drawer-close"
            onClick={close}
            aria-label="Close assistant"
            title="Close"
          >
            &times;
          </button>
        </div>
      </header>

      <MessageList messages={messages} streaming={streaming} />

      {error && (
        <div className="assistant-drawer-error" role="alert">
          {error}
        </div>
      )}

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
    </aside>
  );
}
