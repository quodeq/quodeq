import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { buildMetaResponse, matchCommands, parseMetaCommand } from '../commands.js';

/**
 * AssistantDrawer.jsx (AssistantPane)'s composer state: the draft text, the
 * slash-command menu, and the send/keydown/change handlers. Extracted
 * verbatim; split into these smaller pieces purely to fit the size ratchet's
 * per-function line cap -- same logic, same effects, same conditions.
 */

// Give the prompt keyboard focus when this pane becomes the frontmost tab
// (drawer open or tab switch) so the user can type immediately without
// clicking in. The parent flips display:none→flex in the same commit, so by
// the time this effect runs the textarea is laid out and focusable. Skip
// while streaming (the textarea is disabled then); refocus once it ends.
//
// Also auto-grows the composer with its content (capped in CSS via
// max-height). Keyed on draft so external prefills (welcome cards, slash
// rows) resize too, not only direct typing.
function useComposerFocusEffects({ active, streaming, draft, inputRef }) {
  useEffect(() => {
    if (active && !streaming) inputRef.current?.focus();
  }, [active, streaming]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [draft]);
}

// The slash-command menu's own key handling (arrow nav, escape, tab/enter to
// accept). Returns true when it handled the event, so the caller skips the
// plain Enter-to-send branch.
function handleMenuKeyDown({ event, suggestions, menuIndex, setMenuIndex, setMenuDismissed, acceptSuggestion, draft }) {
  if (event.key === 'ArrowDown') { event.preventDefault(); setMenuIndex((i) => (i + 1) % suggestions.length); return true; }
  if (event.key === 'ArrowUp') { event.preventDefault(); setMenuIndex((i) => (i - 1 + suggestions.length) % suggestions.length); return true; }
  if (event.key === 'Escape') { event.preventDefault(); setMenuDismissed(true); return true; }
  if (event.key === 'Tab') { event.preventDefault(); acceptSuggestion(suggestions[menuIndex]); return true; }
  // Enter completes a partial prefix; once the draft IS the command it sends.
  if (event.key === 'Enter' && !event.shiftKey && draft.trim() !== `/${suggestions[menuIndex].name}`) {
    event.preventDefault(); acceptSuggestion(suggestions[menuIndex]); return true;
  }
  return false;
}

export function useAssistantComposer({ active, streaming, catalog, readOnly, uiState, sendMessage, resetConversation, addLocalExchange }) {
  const [draft, setDraft] = useState('');
  const [menuIndex, setMenuIndex] = useState(0);
  const [menuDismissed, setMenuDismissed] = useState(false);
  const inputRef = useRef(null);

  useComposerFocusEffects({ active, streaming, draft, inputRef });

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
    if (menuVisible && handleMenuKeyDown({ event, suggestions, menuIndex, setMenuIndex, setMenuDismissed, acceptSuggestion, draft })) {
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSend(); }
  }, [menuVisible, suggestions, menuIndex, draft, acceptSuggestion, handleSend]);

  const handleChange = useCallback((event) => {
    setDraft(event.target.value);
    setMenuDismissed(false);
    setMenuIndex(0);
  }, []);

  return {
    draft, setDraft, inputRef, suggestions, menuIndex, menuVisible,
    acceptSuggestion, handleSend, handleKeyDown, handleChange,
  };
}
