import { useState, useEffect } from 'react';
import { resolveDataTheme } from '../utils/themeResolver.js';
import { readString, removeKey, writeString } from '../adapters/storage.js';
import { DATA_THEME_ATTR, PREFERS_DARK_QUERY } from '../constants.js';
import { THEME_MODE, THEME_FAMILY } from '../vocab/theme.js';

const MODE_KEY = 'cc-theme-mode';
const FAMILY_KEY = 'cc-theme-family';
const OLD_THEME_KEY = 'cc-theme';

// Same order as THEME_MODE/THEME_FAMILY's own declaration order (both
// frozen objects), which VALID_MODES/VALID_FAMILIES used to spell out by hand.
const VALID_MODES = Object.values(THEME_MODE);
const VALID_FAMILIES = Object.values(THEME_FAMILY);

const FAMILY_RENAMES = { 'default': 'daruma', 'midnight': 'daruma', 'flynn': 'daruma', 'forest': 'galadriel', 'ember': 'ifrit', 'cyber': 'deckard' };

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
    const old = readString(OLD_THEME_KEY);
    if (old === null) {
      // Migrate old family names to character names
      const currentFamily = readString(FAMILY_KEY);
      if (currentFamily && FAMILY_RENAMES[currentFamily]) {
        writeString(FAMILY_KEY, FAMILY_RENAMES[currentFamily]);
      }
      return;
    }
    const mapped = MIGRATION_MAP[old] || { mode: 'system', family: 'daruma' };
    writeString(MODE_KEY, mapped.mode);
    writeString(FAMILY_KEY, mapped.family);
    removeKey(OLD_THEME_KEY);
  } catch (e) {
    console.warn('Theme migration failed:', e);
  }
}

export { resolveDataTheme };

function applyDataTheme(value) {
  if (value === null) {
    document.documentElement.removeAttribute(DATA_THEME_ATTR);
  } else {
    document.documentElement.setAttribute(DATA_THEME_ATTR, value);
  }
}

/**
 * Owns the theme: the mode (system/light/dark) and the palette family, each
 * persisted and reflected onto <html> through DATA_THEME_ATTR — the single
 * attribute every other consumer reads (see useThemeIsDark).
 *
 * Migrates the pre-split `cc-theme` key on first use and follows the OS
 * preference while the mode is 'system'. Invalid values are ignored rather
 * than applied.
 *
 * @returns {{themeMode: string, applyMode: Function, themeFamily: string, applyFamily: Function}}
 */
export function useAppSettings() {
  function safeGet(key, fallback = '') {
    return readString(key) || fallback;
  }

  // Run migration once before reading new keys
  useState(() => migrateOldTheme());

  const [themeMode, setThemeMode] = useState(safeGet(MODE_KEY, THEME_MODE.SYSTEM));
  const [themeFamily, setThemeFamily] = useState(safeGet(FAMILY_KEY, THEME_FAMILY.DARUMA));

  // Listen for OS color scheme changes when in system mode
  useEffect(() => {
    const mql = window.matchMedia(PREFERS_DARK_QUERY);
    const handler = (e) => {
      if (themeMode === THEME_MODE.SYSTEM) {
        applyDataTheme(resolveDataTheme(THEME_MODE.SYSTEM, themeFamily, e.matches));
      }
    };
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [themeMode, themeFamily]);

  function applyMode(value, storage) {
    if (!VALID_MODES.includes(value)) return;
    setThemeMode(value);
    writeString(MODE_KEY, value, storage);
    const prefersDark = window.matchMedia(PREFERS_DARK_QUERY).matches;
    applyDataTheme(resolveDataTheme(value, themeFamily, prefersDark));
  }

  function applyFamily(value, storage) {
    if (!VALID_FAMILIES.includes(value)) return;
    setThemeFamily(value);
    writeString(FAMILY_KEY, value, storage);
    const prefersDark = window.matchMedia(PREFERS_DARK_QUERY).matches;
    applyDataTheme(resolveDataTheme(themeMode, value, prefersDark));
  }

  return {
    themeMode, applyMode,
    themeFamily, applyFamily,
  };
}
