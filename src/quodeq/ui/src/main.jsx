import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';
import { applyInitialTheme } from './applyInitialTheme.js';
import { ApiProvider } from './api/ApiContext.jsx';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './api/queryClient.js';
import { SidePaneProvider } from './features/side-pane/index.js';
import { AssistantDrawerProvider } from './features/assistant/AssistantDrawerProvider.jsx';
import { PYWEBVIEW_READY_EVENT } from './constants.js';

function isMacPlatform() {
  const ua = navigator.userAgent || '';
  const platform = navigator.platform || '';
  return /Mac|iPhone|iPad|iPod/.test(platform) || /Mac OS X/.test(ua);
}

try {
  applyInitialTheme();
} catch (err) {
  console.warn('[main] initial theme apply failed:', err);
}

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
