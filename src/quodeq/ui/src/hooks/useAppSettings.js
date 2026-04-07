import { useState, useEffect } from 'react';
import { resolveDataTheme } from '../utils/themeResolver.js';

const MODE_KEY = 'cc-theme-mode';
const FAMILY_KEY = 'cc-theme-family';
const OLD_THEME_KEY = 'cc-theme';

const VALID_MODES = ['system', 'light', 'dark'];
const VALID_FAMILIES = ['daruma', 'neo', 'galadriel', 'ifrit', 'deckard'];

const MIGRATION_MAP = {
  system:   { mode: 'system', family: 'daruma' },
  light:    { mode: 'light',  family: 'daruma' },
  dark:     { mode: 'dark',   family: 'daruma' },
  ember:    { mode: 'dark',   family: 'ifrit' },
  forest:   { mode: 'light',  family: 'galadriel' },
  midnight: { mode: 'dark',   family: 'daruma' },
  slate:    { mode: 'light',  family: 'daruma' },
  horizon:  { mode: 'light',  family: 'daruma' },
};

function migrateOldTheme() {
  try {
    const old = localStorage.getItem(OLD_THEME_KEY);
    if (old === null) {
      // Migrate old family names to character names
      const currentFamily = localStorage.getItem(FAMILY_KEY);
      const familyRenames = { 'default': 'daruma', 'midnight': 'daruma', 'flynn': 'daruma', 'forest': 'galadriel', 'ember': 'ifrit', 'cyber': 'deckard' };
      if (currentFamily && familyRenames[currentFamily]) {
        localStorage.setItem(FAMILY_KEY, familyRenames[currentFamily]);
      }
      return;
    }
    const mapped = MIGRATION_MAP[old] || { mode: 'system', family: 'daruma' };
    localStorage.setItem(MODE_KEY, mapped.mode);
    localStorage.setItem(FAMILY_KEY, mapped.family);
    localStorage.removeItem(OLD_THEME_KEY);
  } catch (e) {
    console.warn('Theme migration failed:', e);
  }
}

export { resolveDataTheme };

function applyDataTheme(value) {
  if (value === null) {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', value);
  }
}

export function useAppSettings() {
  function safeGet(key, fallback = '') {
    try { return localStorage.getItem(key) || fallback; } catch (e) { console.warn('localStorage unavailable:', e); return fallback; }
  }

  // Run migration once before reading new keys
  useState(() => migrateOldTheme());

  const [themeMode, setThemeMode] = useState(safeGet(MODE_KEY, 'system'));
  const [themeFamily, setThemeFamily] = useState(safeGet(FAMILY_KEY, 'daruma'));

  // Listen for OS color scheme changes when in system mode
  useEffect(() => {
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e) => {
      if (themeMode === 'system') {
        applyDataTheme(resolveDataTheme('system', themeFamily, e.matches));
      }
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [themeMode, themeFamily]);

  function applyMode(value) {
    if (!VALID_MODES.includes(value)) return;
    setThemeMode(value);
    localStorage.setItem(MODE_KEY, value);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyDataTheme(resolveDataTheme(value, themeFamily, prefersDark));
  }

  function applyFamily(value) {
    if (!VALID_FAMILIES.includes(value)) return;
    setThemeFamily(value);
    localStorage.setItem(FAMILY_KEY, value);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyDataTheme(resolveDataTheme(themeMode, value, prefersDark));
  }

  return {
    themeMode, applyMode,
    themeFamily, applyFamily,
  };
}
