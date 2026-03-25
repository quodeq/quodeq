import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

function applyInitialTheme() {
  const oldTheme = localStorage.getItem('cc-theme');
  if (oldTheme !== null) {
    const map = { system: ['system','daruma'], light: ['light','daruma'], dark: ['dark','daruma'],
      ember: ['dark','ifrit'], forest: ['light','galadriel'], midnight: ['dark','flynn'],
      slate: ['light','daruma'], horizon: ['light','flynn'] };
    const [m, f] = map[oldTheme] || ['system','daruma'];
    localStorage.setItem('cc-theme-mode', m);
    localStorage.setItem('cc-theme-family', f);
    localStorage.removeItem('cc-theme');
  }
  const oldFamily = localStorage.getItem('cc-theme-family');
  const familyMap = { 'default': 'daruma', 'midnight': 'flynn', 'forest': 'galadriel', 'ember': 'ifrit', 'cyber': 'deckard' };
  if (oldFamily && familyMap[oldFamily]) {
    localStorage.setItem('cc-theme-family', familyMap[oldFamily]);
  }
  const mode = localStorage.getItem('cc-theme-mode') || 'system';
  const family = localStorage.getItem('cc-theme-family') || 'daruma';
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const effectiveMode = mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
  // NOTE: This logic must mirror resolveDataTheme() in useAppSettings.js
  if (family === 'daruma') {
    if (mode !== 'system') document.documentElement.setAttribute('data-theme', effectiveMode);
  } else {
    document.documentElement.setAttribute('data-theme', `${family}-${effectiveMode}`);
  }
}

applyInitialTheme();

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode><App /></React.StrictMode>
);
