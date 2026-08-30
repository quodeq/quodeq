import React, { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
import { fetchAssistantCatalog } from '../../api/assistant.js';
import useAssistantProvider from '../settings/hooks/useAssistantProvider.js';
import useTerminalSettings from '../settings/hooks/useTerminalSettings.js';
import { useDrawerHeight } from './useDrawerHeight.js';
import { useDrawerPanels } from './useDrawerPanels.js';
import { useDrawerHotkeys } from './useDrawerHotkeys.js';
import { useAssistantSession } from './useAssistantSession.js';

// Interleaves locally-appended user turns with the stream's messages in the
// order they actually happened: each user turn records how many stream
// messages existed at the moment it was sent, so it's re-inserted at that
// point on every render instead of always being appended at the end.
export function mergeMessages(userTurns, streamMessages) {
  const merged = [];
  let ui = 0;
  for (let i = 0; i <= streamMessages.length; i += 1) {
    while (ui < userTurns.length && userTurns[ui].atIndex === i) {
      merged.push(userTurns[ui]);
      ui += 1;
    }
    if (i < streamMessages.length) merged.push(streamMessages[i]);
  }
  return merged;
}

const AssistantDrawerContext = createContext(null);

export function useAssistantDrawer() {
  const ctx = useContext(AssistantDrawerContext);
  if (ctx === null) {
    throw new Error('useAssistantDrawer must be used inside an <AssistantDrawerProvider>');
  }
  return ctx;
}

export function AssistantDrawerProvider({ children }) {
  const { enabled: assistantEnabled } = useAssistantProvider();
  const { enabled: terminalEnabled } = useTerminalSettings();

  // Each panel has an independent open/selected state. `openPanels` is the set
  // of panels currently in the drawer (in selection order); the drawer is open
  // iff it's non-empty, shows a tab per open panel, and `activeTab` is the one
  // in front. The topbar launchers toggle a panel's membership; clicking a
  // title-bar tab just changes which open panel is active.
  const {
    openPanels, activeTab, isOpen, openTab, selectTab, toggleTopbar,
    open, close, toggle, closeActiveTab, closePanel,
  } = useDrawerPanels({ assistantEnabled, terminalEnabled });

  // Maximized = grow the drawer to (near) full height; toggling restores the
  // previous drag height. Ephemeral (not persisted); reset when the drawer closes.
  const [maximized, setMaximized] = useState(false);
  const toggleMaximized = useCallback(() => setMaximized((m) => !m), []);
  // A closed drawer is never "maximized".
  useEffect(() => { if (openPanels.length === 0 && maximized) setMaximized(false); }, [openPanels.length, maximized]);

  const { height, setHeight } = useDrawerHeight();

  useDrawerHotkeys({ assistantEnabled, terminalEnabled, toggleTopbar });

  // Command/skill catalog for the welcome panel, autocomplete, and
  // meta-commands. Fetched once per app session on first drawer open;
  // failures leave it null and the UI degrades to the built-in commands.
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    if (!isOpen || catalog !== null) return undefined;
    let cancelled = false;
    fetchAssistantCatalog()
      .then((c) => { if (!cancelled) setCatalog(c); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [isOpen, catalog]);

  const session = useAssistantSession();
  const {
    sessionId, sessionMeta, userTurns, localError, stream, turnActive,
    webEnabled, toggleWebEnabled, writeEnabled, toggleWriteEnabled,
    repoInfo, workspace, readOnly, refreshWorkspace,
    addLocalExchange, startSession, sendMessage, stopTurn, resetConversation,
  } = session;

  const messages = useMemo(
    () => mergeMessages(userTurns, stream.messages),
    [userTurns, stream.messages],
  );

  const value = useMemo(() => ({
    isOpen, open, close, toggle, closeActiveTab, closePanel,
    openPanels, activeTab, openTab, selectTab, toggleTopbar, terminalEnabled,
    height, setHeight, maximized, toggleMaximized, setMaximized,
    messages, streaming: turnActive, error: localError || stream.error,
    sessionReady: sessionId != null,
    provider: sessionMeta.provider, model: sessionMeta.model,
    webEnabled, toggleWebEnabled,
    writeEnabled, toggleWriteEnabled, repoInfo, readOnly, workspace, refreshWorkspace,
    sessionId,
    catalog, addLocalExchange,
    startSession, sendMessage, stopTurn, resetConversation,
  }), [isOpen, open, close, toggle, closeActiveTab, closePanel, openPanels, activeTab, openTab, selectTab, toggleTopbar, terminalEnabled, height, setHeight, maximized, toggleMaximized, messages, turnActive, stream.error, localError, sessionId, sessionMeta, webEnabled, toggleWebEnabled, writeEnabled, toggleWriteEnabled, repoInfo, readOnly, workspace, refreshWorkspace, catalog, addLocalExchange, startSession, sendMessage, stopTurn, resetConversation]);

  return (
    <AssistantDrawerContext.Provider value={value}>
      {children}
    </AssistantDrawerContext.Provider>
  );
}
