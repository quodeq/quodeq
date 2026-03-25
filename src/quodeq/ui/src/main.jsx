import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

// Apply saved theme before first render (prevents flash)
// Migration: if old key exists, migrate to new keys
const _oldTheme = localStorage.getItem('cc-theme');
if (_oldTheme !== null) {
  const _map = { system: ['system','default'], light: ['light','default'], dark: ['dark','default'],
    ember: ['dark','ember'], forest: ['light','forest'], midnight: ['dark','midnight'],
    slate: ['light','default'], horizon: ['light','midnight'] };
  const [_m, _f] = _map[_oldTheme] || ['system','default'];
  localStorage.setItem('cc-theme-mode', _m);
  localStorage.setItem('cc-theme-family', _f);
  localStorage.removeItem('cc-theme');
}
const _mode = localStorage.getItem('cc-theme-mode') || 'system';
const _family = localStorage.getItem('cc-theme-family') || 'default';
const _prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
const _effectiveMode = _mode === 'system' ? (_prefersDark ? 'dark' : 'light') : _mode;
if (_family === 'default') {
  if (_effectiveMode === 'dark') document.documentElement.setAttribute('data-theme', 'dark');
} else {
  document.documentElement.setAttribute('data-theme', `${_family}-${_effectiveMode}`);
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode><App /></React.StrictMode>
);
