import React from 'react';
import { useAssistantDrawer } from './AssistantDrawerProvider.jsx';
import { MessageList } from './MessageList.jsx';
import { CommandMenu } from './CommandMenu.jsx';
import { AssistantWelcome } from './AssistantWelcome.jsx';
import { StopIcon } from '../../components/CopyButton.jsx';
import { t } from '../../strings/index.js';
import { useAssistantComposer } from './hooks/useAssistantComposer.js';

function SendIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function AssistantInputRow({
  menuVisible, suggestions, menuIndex, acceptSuggestion, inputRef, draft,
  handleChange, handleKeyDown, streaming, stopTurn, handleSend,
}) {
  return (
    <div className="assistant-drawer-input-row">
      {menuVisible && (
        <CommandMenu suggestions={suggestions} selectedIndex={menuIndex} onPick={acceptSuggestion} />
      )}
      <div className="assistant-composer">
        <span className="assistant-composer-slash" aria-hidden="true">/</span>
        <textarea
          ref={inputRef}
          className="assistant-drawer-input"
          placeholder={t('assistant.inputPlaceholder')}
          value={draft}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          rows={1}
        />
        {streaming ? (
          <button type="button" className="assistant-send-btn assistant-stop-btn"
            onClick={stopTurn}
            aria-label={t('assistant.stopGenerating')} title={t('assistant.stopGenerating')}>
            <StopIcon />
          </button>
        ) : (
          <button type="button"
            className={`assistant-send-btn${draft.trim() ? ' assistant-send-btn--ready' : ''}`}
            onClick={handleSend}
            disabled={!draft.trim()}
            aria-label={t('assistant.send')} title={t('assistant.sendHint')}>
            <SendIcon />
          </button>
        )}
      </div>
      <div className="assistant-composer-hint">
        {t('assistant.inputHint')}
      </div>
    </div>
  );
}

/**
 * Residual assistant content rendered inside the shared BottomDrawer host.
 * The shell (aside, drag-resize, header controls, isOpen gating) lives in
 * `features/drawer/BottomDrawer.jsx`; this component owns the conversation
 * area (welcome panel or MessageList), the error banner, the slash-command
 * menu, and the prompt input.
 *
 * `uiState` is passed in as a prop (current app view context, e.g. active
 * tab) and forwarded verbatim to `sendMessage` on every send.
 *
 * `active` is whether this pane is the frontmost drawer tab. It drives the
 * autofocus effect below; a backgrounded pane (display:none) must not steal
 * focus. Defaults to true so a standalone render still focuses its input.
 */
export function AssistantPane({ uiState, active = true }) {
  const {
    messages, streaming, error, sendMessage, stopTurn,
    catalog, addLocalExchange, resetConversation, readOnly,
  } = useAssistantDrawer();
  const {
    draft, setDraft, inputRef, suggestions, menuIndex, menuVisible,
    acceptSuggestion, handleSend, handleKeyDown, handleChange,
  } = useAssistantComposer({ active, streaming, catalog, readOnly, uiState, sendMessage, resetConversation, addLocalExchange });

  return (
    <>
      {messages.length === 0
        ? <AssistantWelcome catalog={catalog} view={uiState?.view} onPick={setDraft} readOnly={readOnly} />
        : <MessageList messages={messages} streaming={streaming} />}
      {error && <div className="assistant-drawer-error" role="alert">{error}</div>}
      <AssistantInputRow
        menuVisible={menuVisible} suggestions={suggestions} menuIndex={menuIndex} acceptSuggestion={acceptSuggestion}
        inputRef={inputRef} draft={draft} handleChange={handleChange} handleKeyDown={handleKeyDown}
        streaming={streaming} stopTurn={stopTurn} handleSend={handleSend}
      />
    </>
  );
}
