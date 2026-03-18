import { useState } from 'react';
import { MODEL_STORAGE_PREFIX } from '../features/evaluation/components/powerLevels.js';

const THEME_KEY = 'cc-theme';
const AI_CMD_KEY = 'cc-ai-cmd';
const AI_MODEL_KEY = 'cc-ai-model';
const VERIFY_FINDINGS_KEY = 'cc-verify-findings';

export function useAppSettings() {
  const [themePreference, setThemePreference] = useState(
    localStorage.getItem(THEME_KEY) || 'system'
  );
  const [aiCmd, setAiCmd] = useState(localStorage.getItem(AI_CMD_KEY) || '');
  const [aiModel, setAiModel] = useState(localStorage.getItem(AI_MODEL_KEY) || '');
  const [modelFast, setModelFast] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}1`) || '');
  const [modelBalanced, setModelBalanced] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}2`) || '');
  const [modelThorough, setModelThorough] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}3`) || '');
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { return localStorage.getItem(VERIFY_FINDINGS_KEY) === 'true'; } catch { return false; }
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
