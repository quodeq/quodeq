import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';
import { resolveDataTheme } from './utils/themeResolver.js';
import { ApiProvider } from './api/ApiContext.jsx';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './api/queryClient.js';
import { SidePaneProvider } from './features/side-pane/index.js';
import { AssistantDrawerProvider } from './features/assistant/AssistantDrawerProvider.jsx';
import { DATA_THEME_ATTR, PREFERS_DARK_QUERY, PYWEBVIEW_READY_EVENT } from './constants.js';
import { THEME_MODE, THEME_FAMILY } from './vocab/theme.js';

const LS_THEME = 'cc-theme';
const LS_THEME_MODE = 'cc-theme-mode';
const LS_THEME_FAMILY = 'cc-theme-family';

// Retired family: never a THEME_FAMILY member (useAppSettings.js's
// FAMILY_RENAMES folds it into daruma), but the pre-boot migration below
// still has to route old midnight/horizon selections through it exactly as
// it always has, so it needs a name of its own.
const LEGACY_FAMILY_FLYNN = 'flynn';

const LEGACY_THEME_MAP = {
  system: [THEME_MODE.SYSTEM, THEME_FAMILY.DARUMA],
  light: [THEME_MODE.LIGHT, THEME_FAMILY.DARUMA],
  dark: [THEME_MODE.DARK, THEME_FAMILY.DARUMA],
  ember: [THEME_MODE.DARK, THEME_FAMILY.IFRIT],
  forest: [THEME_MODE.LIGHT, THEME_FAMILY.GALADRIEL],
  midnight: [THEME_MODE.DARK, LEGACY_FAMILY_FLYNN],
  slate: [THEME_MODE.LIGHT, THEME_FAMILY.DARUMA],
  horizon: [THEME_MODE.LIGHT, LEGACY_FAMILY_FLYNN],
};

const LEGACY_FAMILY_MAP = {
  default: THEME_FAMILY.DARUMA,
  midnight: LEGACY_FAMILY_FLYNN,
  forest: THEME_FAMILY.GALADRIEL,
  ember: THEME_FAMILY.IFRIT,
  cyber: THEME_FAMILY.DECKARD,
};

function isMacPlatform() {
  const ua = navigator.userAgent || '';
  const platform = navigator.platform || '';
  return /Mac|iPhone|iPad|iPod/.test(platform) || /Mac OS X/.test(ua);
}

function applyInitialTheme(storage = localStorage, mediaQuery = window.matchMedia) {
  const oldTheme = storage.getItem(LS_THEME);
  if (oldTheme !== null) {
    const [m, f] = LEGACY_THEME_MAP[oldTheme] || [THEME_MODE.SYSTEM, THEME_FAMILY.DARUMA];
    storage.setItem(LS_THEME_MODE, m);
    storage.setItem(LS_THEME_FAMILY, f);
    storage.removeItem(LS_THEME);
  }
  const oldFamily = storage.getItem(LS_THEME_FAMILY);
  if (oldFamily && LEGACY_FAMILY_MAP[oldFamily]) {
    storage.setItem(LS_THEME_FAMILY, LEGACY_FAMILY_MAP[oldFamily]);
  }
  const mode = storage.getItem(LS_THEME_MODE) || THEME_MODE.SYSTEM;
  const family = storage.getItem(LS_THEME_FAMILY) || THEME_FAMILY.DARUMA;
  const prefersDark = mediaQuery(PREFERS_DARK_QUERY).matches;
  const dataTheme = resolveDataTheme(mode, family, prefersDark);
  if (dataTheme !== null) {
    document.documentElement.setAttribute(DATA_THEME_ATTR, dataTheme);
  }
}

applyInitialTheme();

// Tag <html> with the host platform and an `in-webview` class so CSS can
// apply native-shell-only styling. The window now uses native OS chrome on
// every platform, so nothing in-page reserves space for window controls;
// these classes remain for platform/shell-conditional styling.
try {
  if (isMacPlatform()) document.documentElement.classList.add('platform-mac');
} catch (err) {
  console.warn('[main] platform detection failed:', err); // progressive enhancement only
}

// pywebview injects `window.pywebview` before PYWEBVIEW_READY_EVENT fires.
// Listen for that event AND probe once on load in case the script
// loaded after the injection.
function markWebview() {
  if (window.pywebview) document.documentElement.classList.add('in-webview');
}
markWebview();
window.addEventListener(PYWEBVIEW_READY_EVENT, markWebview);

// The native OS title bar has no in-app back/forward, so keep the
// Cmd+[ / Cmd+] history shortcuts the old injected chrome provided.
// Only inside the native shell — in a browser these are already native.
document.addEventListener('keydown', (e) => {
  if (!window.pywebview) return;
  const mod = isMacPlatform() ? e.metaKey : e.ctrlKey;
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
          <AssistantDrawerProvider>
            <App />
          </AssistantDrawerProvider>
        </SidePaneProvider>
      </ApiProvider>
    </QueryClientProvider>
  </React.StrictMode>
);
