import { useState, useEffect } from 'react';
import { MODEL_STORAGE_PREFIX } from '../features/evaluation/components/powerLevels.js';

const MODE_KEY = 'cc-theme-mode';
const FAMILY_KEY = 'cc-theme-family';
const OLD_THEME_KEY = 'cc-theme';
const AI_CMD_KEY = 'cc-ai-cmd';
const AI_MODEL_KEY = 'cc-ai-model';
const VERIFY_FINDINGS_KEY = 'cc-verify-findings';

const VALID_MODES = ['system', 'light', 'dark'];
const VALID_FAMILIES = ['default', 'midnight', 'neo', 'forest', 'ember'];

const MIGRATION_MAP = {
  system:   { mode: 'system', family: 'default' },
  light:    { mode: 'light',  family: 'default' },
  dark:     { mode: 'dark',   family: 'default' },
  ember:    { mode: 'dark',   family: 'ember' },
  forest:   { mode: 'light',  family: 'forest' },
  midnight: { mode: 'dark',   family: 'midnight' },
  slate:    { mode: 'light',  family: 'default' },
  horizon:  { mode: 'light',  family: 'midnight' },
};

function migrateOldTheme() {
  try {
    const old = localStorage.getItem(OLD_THEME_KEY);
    if (old === null) return;
    const mapped = MIGRATION_MAP[old] || { mode: 'system', family: 'default' };
    localStorage.setItem(MODE_KEY, mapped.mode);
    localStorage.setItem(FAMILY_KEY, mapped.family);
    localStorage.removeItem(OLD_THEME_KEY);
  } catch (e) {
    console.warn('Theme migration failed:', e);
  }
}

/** Compute the data-theme attribute value from mode + family + OS preference. */
export function resolveDataTheme(mode, family, prefersDark) {
  const effectiveMode = mode === 'system' ? (prefersDark ? 'dark' : 'light') : mode;
  if (family === 'default') {
    return effectiveMode === 'light' ? null : 'dark';
  }
  return `${family}-${effectiveMode}`;
}

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
  const [themeFamily, setThemeFamily] = useState(safeGet(FAMILY_KEY, 'default'));
  const [aiCmd, setAiCmd] = useState(safeGet(AI_CMD_KEY));
  const [aiModel, setAiModel] = useState(safeGet(AI_MODEL_KEY));
  const [modelFast, setModelFast] = useState(safeGet(`${MODEL_STORAGE_PREFIX}1`));
  const [modelBalanced, setModelBalanced] = useState(safeGet(`${MODEL_STORAGE_PREFIX}2`));
  const [modelThorough, setModelThorough] = useState(safeGet(`${MODEL_STORAGE_PREFIX}3`));
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { const v = localStorage.getItem(VERIFY_FINDINGS_KEY); return v === null ? true : v === 'true'; } catch { return true; }
  });

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

  function applyAiCmd(value) {
    setAiCmd(value);
    if (value) {
      localStorage.setItem(AI_CMD_KEY, value);
    } else {
      localStorage.removeItem(AI_CMD_KEY);
    }
  }

  function applyVerifyFindings(value) {
    setVerifyFindings(value);
    localStorage.setItem(VERIFY_FINDINGS_KEY, value ? 'true' : 'false');
  }

  return {
    themeMode, applyMode,
    themeFamily, applyFamily,
    aiCmd, applyAiCmd,
    aiModel, setAiModel,
    modelFast, setModelFast,
    modelBalanced, setModelBalanced,
    modelThorough, setModelThorough,
    verifyFindings, applyVerifyFindings,
  };
}
