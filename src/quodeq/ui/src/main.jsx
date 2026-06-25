import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';
import { resolveDataTheme } from './utils/themeResolver.js';
import { ApiProvider } from './api/ApiContext.jsx';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './api/queryClient.js';
import { SidePaneProvider } from './features/side-pane/index.js';

const LS_THEME = 'cc-theme';
const LS_THEME_MODE = 'cc-theme-mode';
const LS_THEME_FAMILY = 'cc-theme-family';

const THEME_MODES = { SYSTEM: 'system', LIGHT: 'light', DARK: 'dark' };
const THEME_FAMILIES = { DARUMA: 'daruma', FLYNN: 'flynn', GALADRIEL: 'galadriel', IFRIT: 'ifrit', DECKARD: 'deckard' };

const LEGACY_THEME_MAP = {
  system: [THEME_MODES.SYSTEM, THEME_FAMILIES.DARUMA],
  light: [THEME_MODES.LIGHT, THEME_FAMILIES.DARUMA],
  dark: [THEME_MODES.DARK, THEME_FAMILIES.DARUMA],
  ember: [THEME_MODES.DARK, THEME_FAMILIES.IFRIT],
  forest: [THEME_MODES.LIGHT, THEME_FAMILIES.GALADRIEL],
  midnight: [THEME_MODES.DARK, THEME_FAMILIES.FLYNN],
  slate: [THEME_MODES.LIGHT, THEME_FAMILIES.DARUMA],
  horizon: [THEME_MODES.LIGHT, THEME_FAMILIES.FLYNN],
};

const LEGACY_FAMILY_MAP = {
  default: THEME_FAMILIES.DARUMA,
  midnight: THEME_FAMILIES.FLYNN,
  forest: THEME_FAMILIES.GALADRIEL,
  ember: THEME_FAMILIES.IFRIT,
  cyber: THEME_FAMILIES.DECKARD,
};

function applyInitialTheme(storage = localStorage, mediaQuery = window.matchMedia) {
  const oldTheme = storage.getItem(LS_THEME);
  if (oldTheme !== null) {
    const [m, f] = LEGACY_THEME_MAP[oldTheme] || [THEME_MODES.SYSTEM, THEME_FAMILIES.DARUMA];
    storage.setItem(LS_THEME_MODE, m);
    storage.setItem(LS_THEME_FAMILY, f);
    storage.removeItem(LS_THEME);
  }
  const oldFamily = storage.getItem(LS_THEME_FAMILY);
  if (oldFamily && LEGACY_FAMILY_MAP[oldFamily]) {
    storage.setItem(LS_THEME_FAMILY, LEGACY_FAMILY_MAP[oldFamily]);
  }
  const mode = storage.getItem(LS_THEME_MODE) || THEME_MODES.SYSTEM;
  const family = storage.getItem(LS_THEME_FAMILY) || THEME_FAMILIES.DARUMA;
  const prefersDark = mediaQuery('(prefers-color-scheme: dark)').matches;
  const dataTheme = resolveDataTheme(mode, family, prefersDark);
  if (dataTheme !== null) {
    document.documentElement.setAttribute('data-theme', dataTheme);
  }
}

applyInitialTheme();

// Tag <html> with the host platform and an `in-webview` class so CSS can
// apply native-shell-only styling. The window now uses native OS chrome on
// every platform, so nothing in-page reserves space for window controls;
// these classes remain for platform/shell-conditional styling.
try {
  const ua = navigator.userAgent || '';
  const platform = navigator.platform || '';
  const isMac = /Mac|iPhone|iPad|iPod/.test(platform) || /Mac OS X/.test(ua);
  if (isMac) document.documentElement.classList.add('platform-mac');
} catch {
  // ignore — platform detection is a progressive enhancement
}

// pywebview injects `window.pywebview` before `pywebviewready` fires.
// Listen for that event AND probe once on load in case the script
// loaded after the injection.
function markWebview() {
  if (window.pywebview) document.documentElement.classList.add('in-webview');
}
markWebview();
window.addEventListener('pywebviewready', markWebview);

// The native OS title bar has no in-app back/forward, so keep the
// Cmd+[ / Cmd+] history shortcuts the old injected chrome provided.
// Only inside the native shell — in a browser these are already native.
document.addEventListener('keydown', (e) => {
  if (!window.pywebview) return;
  const isMac = /Mac|iPhone|iPad|iPod/.test(navigator.platform);
  const mod = isMac ? e.metaKey : e.ctrlKey;
  if (mod && e.key === '[') { e.preventDefault(); history.back(); }
  if (mod && e.key === ']') { e.preventDefault(); history.forward(); }
});

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ApiProvider>
        <SidePaneProvider>
          <App />
        </SidePaneProvider>
      </ApiProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
