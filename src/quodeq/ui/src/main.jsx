import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

const LS_THEME = 'cc-theme';
const LS_THEME_MODE = 'cc-theme-mode';
const LS_THEME_FAMILY = 'cc-theme-family';

function applyInitialTheme() {
  const oldTheme = localStorage.getItem(LS_THEME);
  if (oldTheme !== null) {
    const map = { system: ['system','daruma'], light: ['light','daruma'], dark: ['dark','daruma'],
      ember: ['dark','ifrit'], forest: ['light','galadriel'], midnight: ['dark','flynn'],
      slate: ['light','daruma'], horizon: ['light','flynn'] };
    const [m, f] = map[oldTheme] || ['system','daruma'];
    localStorage.setItem(LS_THEME_MODE, m);
    localStorage.setItem(LS_THEME_FAMILY, f);
    localStorage.removeItem(LS_THEME);
  }
  const oldFamily = localStorage.getItem(LS_THEME_FAMILY);
  const familyMap = { 'default': 'daruma', 'midnight': 'flynn', 'forest': 'galadriel', 'ember': 'ifrit', 'cyber': 'deckard' };
  if (oldFamily && familyMap[oldFamily]) {
    localStorage.setItem(LS_THEME_FAMILY, familyMap[oldFamily]);
  }
  const mode = localStorage.getItem(LS_THEME_MODE) || 'system';
  const family = localStorage.getItem(LS_THEME_FAMILY) || 'daruma';
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
