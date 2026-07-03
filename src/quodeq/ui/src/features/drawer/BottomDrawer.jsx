import React, { useCallback, useRef, lazy, Suspense } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../settings/hooks/useAssistantProvider.js';
import useTerminalSettings from '../settings/hooks/useTerminalSettings.js';
import { AssistantPane } from '../assistant/AssistantDrawer.jsx';
import { ChevronUpIcon, ChevronDownIcon } from '../../components/CopyButton.jsx';

const TerminalPane = lazy(() => import('../terminal/TerminalPane.jsx'));

/**
 * Shared bottom drawer host: a resizable full-width shell that hosts the
 * Assistant and Terminal panels. Only the ACTIVE (topbar-selected) panel is
 * shown; the inactive one is kept mounted and hidden with `display:none`
 * (never unmounted) so the terminal's xterm buffer and PTY-attached socket
 * survive a tab switch.
 */
export function BottomDrawer({ uiState }) {
  const { isOpen, height, setHeight, close, activeTab,
          maximized, toggleMaximized, setMaximized } = useAssistantDrawer();
  const { enabled: assistantEnabled } = useAssistantProvider();
  const { enabled: terminalEnabled } = useTerminalSettings();
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
  const tab = (!assistantEnabled && terminalEnabled) ? 'terminal'
            : (!terminalEnabled && assistantEnabled) ? 'assistant' : activeTab;

  return (
    <aside className={`bottom-drawer assistant-drawer${maximized ? ' bottom-drawer--maximized' : ''}`}
      style={maximized ? undefined : { height }}>
      <div className="assistant-drawer-drag" onPointerDown={handleDragStart}
        role="separator" aria-orientation="horizontal" aria-label="Resize drawer" />
      <header className="assistant-drawer-header">
        {/* The drawer shows only the ACTIVE (topbar-selected) panel; the
            header just labels it. Switching between Assistant/Terminal is done
            with the topbar launcher buttons, which highlight the active one. */}
        <span className="drawer-active-tab">
          {tab === 'terminal' ? '❯_ Terminal' : '✦ Assistant'}
        </span>
        <div className="assistant-drawer-controls">
          <button type="button" className="assistant-drawer-btn" onClick={toggleMaximized}
            aria-label={maximized ? 'Restore drawer' : 'Maximize drawer'}
            aria-pressed={maximized}
            title={maximized ? 'Restore' : 'Maximize'}>
            {maximized ? <ChevronDownIcon /> : <ChevronUpIcon />}
          </button>
          <button type="button" className="assistant-drawer-btn" onClick={close}
            aria-label="Close drawer" title="Close">&times;</button>
        </div>
      </header>
      {assistantEnabled && (
        <div className="drawer-panel" style={{ display: tab === 'assistant' ? 'flex' : 'none' }}>
          <AssistantPane uiState={uiState} />
        </div>
      )}
      {terminalEnabled && (
        <div className="drawer-panel" style={{ display: tab === 'terminal' ? 'flex' : 'none' }}>
          <Suspense fallback={<div className="tty-disabled">Loading terminal…</div>}>
            <TerminalPane active={tab === 'terminal'} />
          </Suspense>
        </div>
      )}
    </aside>
  );
}
