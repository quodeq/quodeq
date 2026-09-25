import { createContext, useContext, useEffect, useMemo, useState, useCallback } from 'react';
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

// Maximized = grow the drawer to (near) full height; toggling restores the
// previous drag height. Ephemeral (not persisted); reset when the drawer closes.
function useDrawerMaximized(openPanelsLength) {
  const [maximized, setMaximized] = useState(false);
  const toggleMaximized = useCallback(() => setMaximized((m) => !m), []);
  // A closed drawer is never "maximized".
  useEffect(() => { if (openPanelsLength === 0 && maximized) setMaximized(false); }, [openPanelsLength, maximized]);
  return { maximized, setMaximized, toggleMaximized };
}

// Command/skill catalog for the welcome panel, autocomplete, and
// meta-commands. Fetched once per app session on first drawer open;
// failures leave it null and the UI degrades to the built-in commands.
function useAssistantCatalog(isOpen) {
  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    if (!isOpen || catalog !== null) return undefined;
    let cancelled = false;
    fetchAssistantCatalog()
      .then((c) => { if (!cancelled) setCatalog(c); })
      .catch((err) => {
        console.warn('[AssistantDrawerProvider] catalog fetch failed:', err);
      });
    return () => { cancelled = true; };
  }, [isOpen, catalog]);
  return catalog;
}

// The fields the drawer context carries from the chrome and the
// conversation hooks; the memoised value is rebuilt only when one changes.
const CHROME_FIELDS = [
  'isOpen', 'open', 'close', 'toggle', 'closeActiveTab', 'closePanel',
  'openPanels', 'activeTab', 'openTab', 'selectTab', 'toggleTopbar', 'terminalEnabled',
  'height', 'setHeight', 'maximized', 'toggleMaximized', 'setMaximized',
];
const CONVERSATION_FIELDS = [
  'messages', 'turnActive', 'localError', 'sessionId', 'sessionMeta',
  'webEnabled', 'toggleWebEnabled', 'writeEnabled', 'toggleWriteEnabled',
  'repoInfo', 'readOnly', 'workspace', 'refreshWorkspace',
  'catalog', 'addLocalExchange', 'startSession', 'sendMessage', 'stopTurn', 'resetConversation',
];

function pickFields(source, names) {
  return Object.fromEntries(names.map((name) => [name, source[name]]));
}

// The context value the drawer exposes. Everything the caller passes is
// forwarded as-is except the few fields that are renamed or derived here.
function buildDrawerContextValue({
  turnActive, localError, streamError, sessionId, sessionMeta, ...passthrough
}) {
  return {
    ...passthrough,
    streaming: turnActive,
    error: localError || streamError,
    sessionReady: sessionId != null,
    provider: sessionMeta.provider,
    model: sessionMeta.model,
    sessionId,
  };
}

// Drawer chrome: which panels are open, the drag height, the maximize toggle
// and the global hotkeys, gated on the two feature switches.
function useDrawerChrome() {
  const { enabled: assistantEnabled } = useAssistantProvider();
  const { enabled: terminalEnabled } = useTerminalSettings();
  // Each panel has an independent open/selected state — see useDrawerPanels.js.
  const panels = useDrawerPanels({ assistantEnabled, terminalEnabled });
  const { maximized, setMaximized, toggleMaximized } = useDrawerMaximized(panels.openPanels.length);
  const { height, setHeight } = useDrawerHeight();
  useDrawerHotkeys({ assistantEnabled, terminalEnabled, toggleTopbar: panels.toggleTopbar });
  return { ...panels, terminalEnabled, maximized, setMaximized, toggleMaximized, height, setHeight };
}

// The conversation: the catalog (fetched on first open), the session, and the
// message list with the local user turns interleaved.
function useAssistantConversation(isOpen) {
  const catalog = useAssistantCatalog(isOpen);
  const session = useAssistantSession();
  const { userTurns, stream } = session;
  const messages = useMemo(() => mergeMessages(userTurns, stream.messages), [userTurns, stream.messages]);
  return { ...session, catalog, messages };
}

export function AssistantDrawerProvider({ children }) {
  const chrome = useDrawerChrome();
  const conversation = useAssistantConversation(chrome.isOpen);

  const fields = {
    ...pickFields(chrome, CHROME_FIELDS),
    ...pickFields(conversation, CONVERSATION_FIELDS),
    streamError: conversation.stream.error,
  };
  const value = useMemo(() => buildDrawerContextValue(fields), Object.values(fields));

  return (
    <AssistantDrawerContext.Provider value={value}>
      {children}
    </AssistantDrawerContext.Provider>
  );
}
