import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

// Apply saved theme before first render (prevents flash)
// Migration: if old key exists, migrate to new keys
const _oldTheme = localStorage.getItem('cc-theme');
if (_oldTheme !== null) {
  const _map = { system: ['system','daruma'], light: ['light','daruma'], dark: ['dark','daruma'],
    ember: ['dark','ifrit'], forest: ['light','galadriel'], midnight: ['dark','flynn'],
    slate: ['light','daruma'], horizon: ['light','flynn'] };
  const [_m, _f] = _map[_oldTheme] || ['system','daruma'];
  localStorage.setItem('cc-theme-mode', _m);
  localStorage.setItem('cc-theme-family', _f);
  localStorage.removeItem('cc-theme');
}
// Migrate old family names to character names
const _oldFamily = localStorage.getItem('cc-theme-family');
const _familyMap = { 'default': 'daruma', 'midnight': 'flynn', 'forest': 'galadriel', 'ember': 'ifrit', 'cyber': 'deckard' };
if (_oldFamily && _familyMap[_oldFamily]) {
  localStorage.setItem('cc-theme-family', _familyMap[_oldFamily]);
}
const _mode = localStorage.getItem('cc-theme-mode') || 'system';
const _family = localStorage.getItem('cc-theme-family') || 'daruma';
const _prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const _effectiveMode = _mode === 'system' ? (_prefersDark ? 'dark' : 'light') : _mode;
// NOTE: This logic must mirror resolveDataTheme() in useAppSettings.js
if (_family === 'daruma') {
  // System mode: don't set attribute, let @media (prefers-color-scheme) drive
  // Explicit mode: set 'light' or 'dark' to override OS preference
  if (_mode !== 'system') document.documentElement.setAttribute('data-theme', _effectiveMode);
} else {
  document.documentElement.setAttribute('data-theme', `${_family}-${_effectiveMode}`);
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode><App /></React.StrictMode>
);
