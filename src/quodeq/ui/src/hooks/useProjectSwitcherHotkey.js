import { useEffect } from 'react';

const SWITCHER_KEY = 'p';

/** True on macOS, where the modifier is Cmd; everywhere else it is Ctrl. */
export function isMacPlatform() {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform || '') || /Mac OS X/.test(navigator.userAgent || '');
}

/** Whether `e` is the switcher shortcut: Cmd+P on macOS, Ctrl+P elsewhere. */
export function isSwitcherHotkey(e) {
  const mod = isMacPlatform() ? e.metaKey : e.ctrlKey;
  return mod && !e.shiftKey && !e.altKey && e.key?.toLowerCase() === SWITCHER_KEY;
}

/**
 * Cmd+P / Ctrl+P opens the project switcher instead of the print dialog.
 * Only bound while `enabled` (there is a project crumb to open from), so with
 * no projects the browser's own print shortcut still works.
 * @param {boolean} enabled
 * @param {() => void} open
 */
export function useProjectSwitcherHotkey(enabled, open) {
  useEffect(() => {
    if (!enabled) return undefined;
    const onKey = (e) => {
      if (!isSwitcherHotkey(e)) return;
      e.preventDefault();
      open();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [enabled, open]);
}
