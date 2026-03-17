import { useState } from 'react';
import { MODEL_STORAGE_PREFIX } from '../features/evaluation/components/powerLevels.js';

export function useAppSettings() {
  const [themePreference, setThemePreference] = useState(
    localStorage.getItem('cc-theme') || 'system'
  );
  const [aiCmd, setAiCmd] = useState(localStorage.getItem('cc-ai-cmd') || '');
  const [aiModel, setAiModel] = useState(localStorage.getItem('cc-ai-model') || '');
  const [modelFast, setModelFast] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}1`) || '');
  const [modelBalanced, setModelBalanced] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}2`) || '');
  const [modelThorough, setModelThorough] = useState(localStorage.getItem(`${MODEL_STORAGE_PREFIX}3`) || '');
  const [verifyFindings, setVerifyFindings] = useState(() => {
    try { return localStorage.getItem('cc-verify-findings') !== 'false'; } catch { return true; }
  });

  function applyTheme(value) {
    setThemePreference(value);
    if (value === 'system') {
      localStorage.removeItem('cc-theme');
      document.documentElement.removeAttribute('data-theme');
    } else {
      localStorage.setItem('cc-theme', value);
      document.documentElement.setAttribute('data-theme', value);
    }
  }

  function applyAiCmd(value) {
    setAiCmd(value);
    if (value) {
      localStorage.setItem('cc-ai-cmd', value);
    } else {
      localStorage.removeItem('cc-ai-cmd');
    }
  }

  function applyVerifyFindings(value) {
    setVerifyFindings(value);
    localStorage.setItem('cc-verify-findings', value ? 'true' : 'false');
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
