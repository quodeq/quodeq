import { useEffect } from 'react';
import { KNOWN_TABS } from './useAppState.js';

// Bridge for the native shell: the macOS menu bar lives in the Python
// process (pywebview/Cocoa) and can't call navTab directly, so it dispatches
// a `quodeq:navigate` CustomEvent through evaluate_js (see
// _webview_window._install_macos_help_menu). Only known tab ids are routed;
// anything else is dropped so a stale or malformed event can't break the
// nav stack.
export function useNativeNavBridge(navTab) {
  useEffect(() => {
    const handler = (event) => {
      if (KNOWN_TABS.includes(event?.detail)) navTab(event.detail);
    };
    window.addEventListener('quodeq:navigate', handler);
    return () => window.removeEventListener('quodeq:navigate', handler);
  }, [navTab]);
}
