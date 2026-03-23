import { useState } from 'react';
import { MODEL_STORAGE_PREFIX } from '../features/evaluation/components/powerLevels.js';

const THEME_KEY = 'cc-theme';
const AI_CMD_KEY = 'cc-ai-cmd';
const AI_MODEL_KEY = 'cc-ai-model';
const VERIFY_FINDINGS_KEY = 'cc-verify-findings';

export function useAppSettings() {
  function safeGet(key, fallback = '') {
    try { return localStorage.getItem(key) || fallback; } catch (e) { console.warn('localStorage unavailable:', e); return fallback; }
  }
  const [themePreference, setThemePreference] = useState(safeGet(THEME_KEY, 'system'));
  const [aiCmd, setAiCmd] = useState(safeGet(AI_CMD_KEY));
  const [aiModel, setAiModel] = useState(safeGet(AI_MODEL_KEY));
  const [modelFast, setModelFast] = useState(safeGet(`${MODEL_STORAGE_PREFIX}1`));
  const [modelBalanced, setModelBalanced] = useState(safeGet(`${MODEL_STORAGE_PREFIX}2`));
  const [modelThorough, setModelThorough] = useState(safeGet(`${MODEL_STORAGE_PREFIX}3`));
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { const v = localStorage.getItem(VERIFY_FINDINGS_KEY); return v === null ? true : v === 'true'; } catch { return true; }
  });

  function applyTheme(value) {
    setThemePreference(value);
    if (value === 'system') {
      localStorage.removeItem(THEME_KEY);
      document.documentElement.removeAttribute('data-theme');
    } else {
      localStorage.setItem(THEME_KEY, value);
      document.documentElement.setAttribute('data-theme', value);
    }
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
    themePreference, applyTheme,
    aiCmd, applyAiCmd,
    aiModel, setAiModel,
    modelFast, setModelFast,
    modelBalanced, setModelBalanced,
    modelThorough, setModelThorough,
    verifyFindings, applyVerifyFindings,
  };
}
