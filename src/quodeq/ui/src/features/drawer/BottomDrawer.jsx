import React, { useCallback, useEffect, useRef, lazy, Suspense } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import { AssistantPane } from '../assistant/AssistantDrawer.jsx';
import AssistantHeader from '../assistant/AssistantHeader.jsx';
import { t } from '../../strings/index.js';

const TerminalPane = lazy(() => import('../terminal/TerminalPane.jsx'));

/**
 * Shared bottom drawer host: a resizable full-width shell that hosts the
 * open panels. There is no shared header — each panel renders its own (with
 * a compact panel switcher inside it). The active panel is shown; any other
 * open panel is kept mounted and hidden with `display:none` (never
 * unmounted) so the terminal's xterm buffers and PTY-attached sockets
 * survive a tab switch.
 */
function useDrawerDrag({ height, setHeight, maximized, setMaximized }) {
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
  // Unmounting mid-drag would leave the window listeners registered and the
  // stale handlers calling setHeight until the next pointerup; drop them.
  useEffect(() => () => {
    window.removeEventListener('pointermove', handleDragMove);
    window.removeEventListener('pointerup', handleDragEnd);
  }, [handleDragMove, handleDragEnd]);

  return handleDragStart;
}

export function BottomDrawer({ uiState, projectName, onOpenSettings }) {
  const { isOpen, height, setHeight, openPanels, activeTab,
          maximized, setMaximized } = useAssistantDrawer();
  const handleDragStart = useDrawerDrag({ height, setHeight, maximized, setMaximized });

  if (!isOpen) return null;
  // Guard against a transient render where activeTab isn't (yet) an open panel.
  const active = openPanels.includes(activeTab) ? activeTab : openPanels[openPanels.length - 1];

  return (
    <aside className={`bottom-drawer assistant-drawer${maximized ? ' bottom-drawer--maximized' : ''}`}
      style={maximized ? undefined : { height }}>
      <div className="assistant-drawer-drag" onPointerDown={handleDragStart}
        role="separator" aria-orientation="horizontal" aria-label={t('common.resizeDrawer')} />
      {openPanels.includes('assistant') && (
        <div className="drawer-panel" style={{ display: active === 'assistant' ? 'flex' : 'none' }}>
          <AssistantHeader selectedProject={projectName ?? uiState?.selectedProject} onOpenSettings={onOpenSettings} />
          <AssistantPane uiState={uiState} active={active === 'assistant'} />
        </div>
      )}
      {openPanels.includes('terminal') && (
        <div className="drawer-panel" style={{ display: active === 'terminal' ? 'flex' : 'none' }}>
          <Suspense fallback={<div className="tty-disabled">{t('drawer.loadingTerminal')}</div>}>
            <TerminalPane active={active === 'terminal'} />
          </Suspense>
        </div>
      )}
    </aside>
  );
}
