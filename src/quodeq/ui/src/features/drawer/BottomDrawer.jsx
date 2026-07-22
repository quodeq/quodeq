import React, { useCallback, useRef, lazy, Suspense } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import { AssistantPane } from '../assistant/AssistantDrawer.jsx';
import { ChevronDownIcon, GlobeIcon, MaximizeIcon, MinimizeIcon, PencilIcon, RotateCcwIcon } from '../../components/CopyButton.jsx';
import { useSidePane, workspaceDiffSpec } from '../side-pane/index.js';
import Badge from '../../components/Badge.jsx';

const TerminalPane = lazy(() => import('../terminal/TerminalPane.jsx'));

const TAB_LABELS = { assistant: '✦ Assistant', terminal: '❯_ Terminal' };

// Providers where the web toggle does something: claude flips its native
// WebSearch/WebFetch; local providers get in-process search_web/fetch_url.
// Mirrors the backend gate (LOCAL_PROVIDERS in llm_bridge/_providers.py plus
// the claude argv path in adapters/_cli_command.py) — keep the two in sync.
const WEB_PROVIDERS = new Set(['claude', 'ollama', 'omlx', 'llamacpp']);

/**
 * Shared bottom drawer host: a resizable full-width shell that hosts the
 * open panels. The title bar shows a tab per OPEN panel (both only when both
 * are selected on the topbar); clicking a tab activates it. The active panel
 * is shown; any other open panel is kept mounted and hidden with
 * `display:none` (never unmounted) so the terminal's xterm buffer and
 * PTY-attached socket survive a tab switch.
 */
export function BottomDrawer({ uiState }) {
  const { isOpen, height, setHeight, closeActiveTab, openPanels, activeTab, selectTab,
          maximized, toggleMaximized, setMaximized, provider, model,
          streaming, webEnabled, toggleWebEnabled,
          writeEnabled, toggleWriteEnabled, repoInfo, workspace, refreshWorkspace,
          sessionId, sessionReady, resetConversation } = useAssistantDrawer();
  const { addWindow } = useSidePane();
  const dragRef = useRef(null);

  const handleDragMove = useCallback((event) => {
    if (!dragRef.current) return;
    setHeight(dragRef.current.startHeight + (dragRef.current.startY - event.clientY));
  }, [setHeight]);
  const handleDragEnd = useCallback(() => {
    dragRef.current = null;
    window.removeEventListener('pointermove', handleDragMove);
    window.removeEventListener('pointerup', handleDragEnd);
  }, [handleDragMove]);
  const handleDragStart = useCallback((event) => {
    // Manual resize takes over from "maximized" — capture the real rendered
    // height so the drag starts from where the maximized drawer actually is.
    if (maximized) {
      setMaximized(false);
      const h = event.currentTarget.parentElement?.getBoundingClientRect().height ?? height;
      dragRef.current = { startY: event.clientY, startHeight: h };
    } else {
      dragRef.current = { startY: event.clientY, startHeight: height };
    }
    window.addEventListener('pointermove', handleDragMove);
    window.addEventListener('pointerup', handleDragEnd);
  }, [height, maximized, setMaximized, handleDragMove, handleDragEnd]);

  if (!isOpen) return null;
  // Guard against a transient render where activeTab isn't (yet) an open panel.
  const active = openPanels.includes(activeTab) ? activeTab : openPanels[openPanels.length - 1];
  // Header pill: "Provider · model" (provider capitalized for display, e.g.
  // "Claude · sonnet"). Falls back to whichever half is present.
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const modelLabel = [cap(provider), model].filter(Boolean).join(' · ');

  return (
    <aside className={`bottom-drawer assistant-drawer${maximized ? ' bottom-drawer--maximized' : ''}`}
      style={maximized ? undefined : { height }}>
      <div className="assistant-drawer-drag" onPointerDown={handleDragStart}
        role="separator" aria-orientation="horizontal" aria-label="Resize drawer" />
      <header className="assistant-drawer-header">
        {/* One tab per OPEN panel (both only when both are selected on the
            topbar). Clicking a tab activates it without deselecting the other;
            the topbar launchers add/remove panels. */}
        <div className="drawer-tabs" role="tablist">
          {openPanels.map((t) => (
            <button key={t} type="button" role="tab" aria-selected={t === active}
              className={`drawer-tab${t === active ? ' drawer-tab--active' : ''}`}
              onClick={() => selectTab(t)}>{TAB_LABELS[t]}</button>
          ))}
        </div>
        {active === 'assistant' && modelLabel && (
          <Badge variant="tag" tone="accent" className="drawer-model-chip" title={modelLabel}>
            {modelLabel}
          </Badge>
        )}
        {/* Repo attachment is the NORMAL case — only the exception is worth a
            chip. When the session has no repo the assistant's code-reading
            tools are dead, so surface that as a warning with the server's
            reason; stay silent when everything is fine. */}
        {active === 'assistant' && repoInfo && !repoInfo.attached && (
          <Badge variant="tag" tone="warning"
            title={`Repository not attached: ${repoInfo.reason || 'unknown'}`}>
            no repo access
          </Badge>
        )}
        {active === 'assistant' && workspace?.filesChanged > 0 && (
          <button type="button" className="badge badge--tag badge--danger drawer-changes-chip"
            onClick={() => addWindow(workspaceDiffSpec({ sessionId, key: workspace.createdAt, onChanged: refreshWorkspace }))}
            title="Review pending changes">
            {workspace.filesChanged} file{workspace.filesChanged === 1 ? '' : 's'} changed
          </button>
        )}
        <div className="assistant-drawer-controls">
          {active === 'assistant' && (
            <button type="button" className="assistant-drawer-btn"
              onClick={resetConversation}
              aria-label="New conversation"
              title="New conversation (clears the model context)"
              disabled={streaming || !sessionReady}>
              <RotateCcwIcon />
            </button>
          )}
          {active === 'assistant' && repoInfo?.writeAvailable && (
            <button type="button" className="assistant-drawer-btn assistant-drawer-write"
              onClick={toggleWriteEnabled}
              aria-pressed={writeEnabled}
              aria-label="Allow repository edits for this conversation"
              title="Allow repository edits for this conversation (isolated worktree, you review before anything lands)"
              disabled={streaming}>
              <PencilIcon />
            </button>
          )}
          {active === 'assistant' && WEB_PROVIDERS.has(provider) && (
            <button type="button" className="assistant-drawer-btn assistant-drawer-web"
              onClick={toggleWebEnabled}
              aria-pressed={webEnabled}
              aria-label="Allow web access for this conversation"
              title="Allow web access for this conversation"
              disabled={streaming}>
              <GlobeIcon />
            </button>
          )}
          <button type="button" className="assistant-drawer-btn" onClick={toggleMaximized}
            aria-label={maximized ? 'Restore drawer' : 'Maximize drawer'}
            aria-pressed={maximized}
            title={maximized ? 'Restore' : 'Maximize'}>
            {maximized ? <MinimizeIcon /> : <MaximizeIcon />}
          </button>
          {/* Chevron-down, NOT an ×: neither panel is killed by this. The
              terminal's PTY shell and an in-flight assistant turn keep running
              server-side; reopening the tab reattaches to them. */}
          <button type="button" className="assistant-drawer-btn" onClick={closeActiveTab}
            aria-label="Hide tab" title="Hide (keeps running in the background)">
            <ChevronDownIcon />
          </button>
        </div>
      </header>
      {openPanels.includes('assistant') && (
        <div className="drawer-panel" style={{ display: active === 'assistant' ? 'flex' : 'none' }}>
          <AssistantPane uiState={uiState} />
        </div>
      )}
      {openPanels.includes('terminal') && (
        <div className="drawer-panel" style={{ display: active === 'terminal' ? 'flex' : 'none' }}>
          <Suspense fallback={<div className="tty-disabled">Loading terminal…</div>}>
            <TerminalPane active={active === 'terminal'} />
          </Suspense>
        </div>
      )}
    </aside>
  );
}
