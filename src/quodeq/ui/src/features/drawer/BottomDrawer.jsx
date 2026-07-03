import React, { useCallback, useRef, lazy, Suspense } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import useAssistantProvider from '../settings/hooks/useAssistantProvider.js';
import useTerminalSettings from '../settings/hooks/useTerminalSettings.js';
import { AssistantPane } from '../assistant/AssistantDrawer.jsx';

const TerminalPane = lazy(() => import('../terminal/TerminalPane.jsx'));
const MIN_DRAWER_HEIGHT = 160;

/**
 * Shared bottom drawer host: a resizable full-width shell with a tab strip
 * that hosts the Assistant and Terminal panels. The inactive panel is kept
 * mounted and hidden with `display:none` (never unmounted) so the terminal's
 * xterm buffer and PTY-attached socket survive tab switches.
 */
export function BottomDrawer({ uiState }) {
  const { isOpen, height, setHeight, close, activeTab, openTab } = useAssistantDrawer();
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
    dragRef.current = { startY: event.clientY, startHeight: height };
    window.addEventListener('pointermove', handleDragMove);
    window.addEventListener('pointerup', handleDragEnd);
  }, [height, handleDragMove, handleDragEnd]);

  if (!isOpen) return null;
  const tab = (!assistantEnabled && terminalEnabled) ? 'terminal'
            : (!terminalEnabled && assistantEnabled) ? 'assistant' : activeTab;

  return (
    <aside className="bottom-drawer assistant-drawer" style={{ height }}>
      <div className="assistant-drawer-drag" onPointerDown={handleDragStart}
        role="separator" aria-orientation="horizontal" aria-label="Resize drawer" />
      <header className="assistant-drawer-header">
        <div className="drawer-tabs" role="tablist">
          {assistantEnabled && (
            <button type="button" role="tab" aria-selected={tab === 'assistant'}
              className={`drawer-tab${tab === 'assistant' ? ' drawer-tab--active' : ''}`}
              onClick={() => openTab('assistant')}>✦ Assistant</button>
          )}
          {terminalEnabled && (
            <button type="button" role="tab" aria-selected={tab === 'terminal'}
              className={`drawer-tab${tab === 'terminal' ? ' drawer-tab--active' : ''}`}
              onClick={() => openTab('terminal')}>❯_ Terminal</button>
          )}
        </div>
        <div className="assistant-drawer-controls">
          <button type="button" className="assistant-drawer-btn" onClick={() => setHeight(MIN_DRAWER_HEIGHT)}
            aria-label="Minimize" title="Minimize">&#95;</button>
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
