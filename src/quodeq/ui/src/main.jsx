import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import './styles/index.css';
import { resolveDataTheme } from './utils/themeResolver.js';

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

function applyInitialTheme() {
  const oldTheme = localStorage.getItem(LS_THEME);
  if (oldTheme !== null) {
    const [m, f] = LEGACY_THEME_MAP[oldTheme] || [THEME_MODES.SYSTEM, THEME_FAMILIES.DARUMA];
    localStorage.setItem(LS_THEME_MODE, m);
    localStorage.setItem(LS_THEME_FAMILY, f);
    localStorage.removeItem(LS_THEME);
  }
  const oldFamily = localStorage.getItem(LS_THEME_FAMILY);
  if (oldFamily && LEGACY_FAMILY_MAP[oldFamily]) {
    localStorage.setItem(LS_THEME_FAMILY, LEGACY_FAMILY_MAP[oldFamily]);
  }
  const mode = localStorage.getItem(LS_THEME_MODE) || 'system';
  const family = localStorage.getItem(LS_THEME_FAMILY) || 'daruma';
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  const dataTheme = resolveDataTheme(mode, family, prefersDark);
  if (dataTheme !== null) {
    document.documentElement.setAttribute('data-theme', dataTheme);
  }
}

applyInitialTheme();

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element #root not found in DOM');
createRoot(rootEl).render(
  <React.StrictMode><App /></React.StrictMode>
);
