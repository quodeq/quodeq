import React, { useCallback, useMemo, useState } from 'react';
import { useAssistantDrawer } from './AssistantDrawerProvider.jsx';
import { MessageList } from './MessageList.jsx';
import { CommandMenu } from './CommandMenu.jsx';
import { AssistantWelcome } from './AssistantWelcome.jsx';
import { buildMetaResponse, matchCommands, parseMetaCommand } from './commands.js';
import { StopIcon } from '../../components/CopyButton.jsx';

/**
 * Residual assistant content rendered inside the shared BottomDrawer host.
 * The shell (aside, drag-resize, header controls, isOpen gating) lives in
 * `features/drawer/BottomDrawer.jsx`; this component owns the conversation
 * area (welcome panel or MessageList), the error banner, the slash-command
 * menu, and the prompt input.
 *
 * `uiState` is passed in as a prop (current app view context, e.g. active
 * tab) and forwarded verbatim to `sendMessage` on every send.
 */
export function AssistantPane({ uiState }) {
  const {
    messages, streaming, error, sendMessage, stopTurn,
    catalog, addLocalExchange, resetConversation, readOnly,
  } = useAssistantDrawer();
  const [draft, setDraft] = useState('');
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);

  const suggestions = useMemo(
    () => (streaming ? [] : matchCommands(catalog, draft, { readOnly })),
    [catalog, draft, streaming, readOnly],
  );
  const menuVisible = suggestions.length > 0 && !menuDismissed;

  const acceptSuggestion = useCallback((cmd) => {
    setDraft(`/${cmd.name} `);
    setMenuIndex(0);
  }, []);

  const handleSend = useCallback(() => {
    const text = draft.trim();
    if (!text || streaming) return;
    const meta = parseMetaCommand(text);
    if (meta === 'clear') { resetConversation(); setDraft(''); return; }
    if (meta) { addLocalExchange(text, buildMetaResponse(meta, catalog, { readOnly })); setDraft(''); return; }
    sendMessage(text, uiState);
    setDraft('');
  }, [draft, streaming, sendMessage, uiState, catalog, addLocalExchange, resetConversation, readOnly]);

  const handleKeyDown = useCallback((event) => {
    if (menuVisible) {
      if (event.key === 'ArrowDown') { event.preventDefault(); setMenuIndex((i) => (i + 1) % suggestions.length); return; }
      if (event.key === 'ArrowUp') { event.preventDefault(); setMenuIndex((i) => (i - 1 + suggestions.length) % suggestions.length); return; }
      if (event.key === 'Escape') { event.preventDefault(); setMenuDismissed(true); return; }
      if (event.key === 'Tab') { event.preventDefault(); acceptSuggestion(suggestions[menuIndex]); return; }
      // Enter completes a partial prefix; once the draft IS the command it sends.
      if (event.key === 'Enter' && !event.shiftKey && draft.trim() !== `/${suggestions[menuIndex].name}`) {
        event.preventDefault(); acceptSuggestion(suggestions[menuIndex]); return;
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSend(); }
  }, [menuVisible, suggestions, menuIndex, draft, acceptSuggestion, handleSend]);

  const handleChange = useCallback((event) => {
    setDraft(event.target.value);
    setMenuDismissed(false);
    setMenuIndex(0);
  }, []);

  return (
    <>
      {messages.length === 0
        ? <AssistantWelcome catalog={catalog} view={uiState?.view} onPick={setDraft} readOnly={readOnly} />
        : <MessageList messages={messages} streaming={streaming} />}
      {error && <div className="assistant-drawer-error" role="alert">{error}</div>}
      <div className="assistant-drawer-input-row">
        {menuVisible && (
          <CommandMenu suggestions={suggestions} selectedIndex={menuIndex} onPick={acceptSuggestion} />
        )}
        <textarea
          className="assistant-drawer-input"
          placeholder="Ask the assistant…"
          value={draft}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={streaming}
          rows={1}
        />
        {streaming && (
          <button type="button" className="assistant-stop-btn"
            onClick={stopTurn}
            aria-label="Stop generating" title="Stop generating">
            <StopIcon />
          </button>
        )}
      </div>
    </>
  );
}
