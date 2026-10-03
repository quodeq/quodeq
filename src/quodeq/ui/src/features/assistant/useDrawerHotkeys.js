/**
 * Ctrl/Cmd+` opens/toggles the assistant or terminal drawer panel;
 * Ctrl/Cmd+Shift+` targets the terminal specifically. Shared projects get
 * read-only sessions server-side, so the shortcut opens the drawer for any
 * source.
 */
import { useEffect } from 'react';
import { KEY_CODE } from '../../vocab/keyboard.js';
import { DRAWER_PANEL } from './drawerPanelsModel.js';

/**
 * Pure decision: which panel (if any) a keydown event should toggle. Does
 * NOT decide whether to preventDefault() — the browser default must be
 * suppressed whenever the key combo matches, even when no panel resolves
 * (e.g. Ctrl+Shift+` with the terminal feature disabled), so that stays in
 * the hook below, right where the combo is recognised.
 */
export function resolveHotkeyTarget(event, { assistantEnabled, terminalEnabled }) {
  if (event.code !== KEY_CODE.BACKQUOTE || !(event.ctrlKey || event.metaKey)) return null;
  if (event.shiftKey) {
    return terminalEnabled ? DRAWER_PANEL.TERMINAL : null;
  }
  if (assistantEnabled) return DRAWER_PANEL.ASSISTANT;
  if (terminalEnabled) return DRAWER_PANEL.TERMINAL;
  return null;
}

export function useDrawerHotkeys({ assistantEnabled, terminalEnabled, toggleTopbar }) {
  useEffect(() => {
    if (!assistantEnabled && !terminalEnabled) return undefined;
    const handleKeyDown = (e) => {
      if (e.code !== KEY_CODE.BACKQUOTE || !(e.ctrlKey || e.metaKey)) return;
      e.preventDefault();
      const target = resolveHotkeyTarget(e, { assistantEnabled, terminalEnabled });
      if (target) toggleTopbar(target);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [assistantEnabled, terminalEnabled, toggleTopbar]);
}
