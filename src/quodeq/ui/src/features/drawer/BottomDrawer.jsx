import { useCallback, useEffect, useRef, lazy, Suspense } from 'react';
import { useAssistantDrawer } from '../assistant/AssistantDrawerProvider.jsx';
import { AssistantPane } from '../assistant/AssistantDrawer.jsx';
import AssistantHeader from '../assistant/AssistantHeader.jsx';
import { t } from '../../strings/index.js';
import { DRAWER_PANEL } from '../assistant/drawerPanelsModel.js';
import { POINTER_EVENT } from '../../vocab/pointerEvent.js';

const TerminalPane = lazy(() => import('../terminal/TerminalPane.jsx'));

// One keyboard step for the resize handle, matching the mouse-drag path's
// granularity closely enough to feel like the same control.
const RESIZE_STEP_PX = 16;
// Arrow keys that resize the handle, and which way each one moves the top edge.
const RESIZE_KEY_DIRECTION = { ArrowUp: 1, ArrowDown: -1 };

// Where a manual resize starts from. A maximized drawer ignores the stored
// height, so mutating it would move the drawer to a size nobody can see:
// give way to the manual size and measure what is actually rendered.
function resizeStartHeight(handleEl, { height, maximized, setMaximized }) {
  if (!maximized) return height;
  setMaximized(false);
  return handleEl.parentElement?.getBoundingClientRect().height ?? height;
}

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
    window.removeEventListener(POINTER_EVENT.MOVE, handleDragMove);
    window.removeEventListener(POINTER_EVENT.UP, handleDragEnd);
  }, [handleDragMove]);
  const handleDragStart = useCallback((event) => {
    const startHeight = resizeStartHeight(event.currentTarget, { height, maximized, setMaximized });
    dragRef.current = { startY: event.clientY, startHeight };
    window.addEventListener(POINTER_EVENT.MOVE, handleDragMove);
    window.addEventListener(POINTER_EVENT.UP, handleDragEnd);
  }, [height, maximized, setMaximized, handleDragMove, handleDragEnd]);
  // The keyboard path is the same resize, one step at a time.
  const handleResizeKey = useCallback((event) => {
    // hasOwn, not a bare lookup: 'constructor' and friends would otherwise
    // resolve through Object.prototype and resize the drawer to NaN.
    if (!Object.hasOwn(RESIZE_KEY_DIRECTION, event.key)) return;
    const direction = RESIZE_KEY_DIRECTION[event.key];
    event.preventDefault();
    const from = resizeStartHeight(event.currentTarget, { height, maximized, setMaximized });
    setHeight(from + direction * RESIZE_STEP_PX);
  }, [height, maximized, setMaximized, setHeight]);
  // Unmounting mid-drag would leave the window listeners registered and the
  // stale handlers calling setHeight until the next pointerup; drop them.
  useEffect(() => () => {
    window.removeEventListener(POINTER_EVENT.MOVE, handleDragMove);
    window.removeEventListener(POINTER_EVENT.UP, handleDragEnd);
  }, [handleDragMove, handleDragEnd]);

  return { handleDragStart, handleResizeKey };
}

export function BottomDrawer({ uiState, projectName, onOpenSettings }) {
  const { isOpen, height, setHeight, openPanels, activeTab,
          maximized, setMaximized } = useAssistantDrawer();
  const { handleDragStart, handleResizeKey } = useDrawerDrag({ height, setHeight, maximized, setMaximized });

  if (!isOpen) return null;
  // Guard against a transient render where activeTab isn't (yet) an open panel.
  const active = openPanels.includes(activeTab) ? activeTab : openPanels[openPanels.length - 1];

  return (
    <aside className={`bottom-drawer assistant-drawer${maximized ? ' bottom-drawer--maximized' : ''}`}
      style={maximized ? undefined : { height }}>
      <div className="assistant-drawer-drag" onPointerDown={handleDragStart}
        role="separator" tabIndex={0} aria-orientation="horizontal"
        aria-label={t('common.resizeDrawer')} aria-valuenow={height}
        onKeyDown={handleResizeKey} />
      {openPanels.includes(DRAWER_PANEL.ASSISTANT) && (
        <div className="drawer-panel" style={{ display: active === DRAWER_PANEL.ASSISTANT ? 'flex' : 'none' }}>
          <AssistantHeader selectedProject={projectName ?? uiState?.selectedProject} onOpenSettings={onOpenSettings} />
          <AssistantPane uiState={uiState} active={active === DRAWER_PANEL.ASSISTANT} />
        </div>
      )}
      {openPanels.includes(DRAWER_PANEL.TERMINAL) && (
        <div className="drawer-panel" style={{ display: active === DRAWER_PANEL.TERMINAL ? 'flex' : 'none' }}>
          <Suspense fallback={<div className="tty-disabled">{t('drawer.loadingTerminal')}</div>}>
            <TerminalPane active={active === DRAWER_PANEL.TERMINAL} />
          </Suspense>
        </div>
      )}
    </aside>
  );
}
