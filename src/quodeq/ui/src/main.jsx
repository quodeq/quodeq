import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';

// Apply saved theme before first render (prevents flash)
const THEME_STORAGE_KEY = 'cc-theme';
const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
const VALID_THEMES = ['dark', 'light', 'ember', 'forest', 'midnight', 'slate', 'horizon'];
if (VALID_THEMES.includes(savedTheme)) {
  document.documentElement.setAttribute('data-theme', savedTheme);
}

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode><App /></React.StrictMode>
);
