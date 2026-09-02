import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS, DEFAULT_SUBAGENTS } from '../../../constants.js';
import { STORAGE_KEY as POWER_KEY } from '../../evaluation/components/powerLevels.js';
import { tRich } from '../../../strings/rich.jsx';
import { readString, writeString } from '../../../adapters/storage.js';

const DEFAULT_POWER_LEVEL = 2;

const MODEL_HINTS = {
  claude: tRich('settings.modelHintClaude'),
  codex: tRich('settings.modelHintCodex'),
  gemini: tRich('settings.modelHintGemini'),
};

const ANALYSIS_MODEL_HINTS = {
  claude: tRich('settings.analysisModelsHintClaude'),
  codex: tRich('settings.analysisModelsHintCodex'),
  gemini: tRich('settings.analysisModelsHintGemini'),
};

/**
 * CliProviderTab.jsx's power-level/cmd-path-validation state, extracted
 * verbatim.
 */
export function useCliProviderTab({ providerId, state }) {
  const api = useApi();
  const [power, setPower] = useState(() => {
    return Number(readString(POWER_KEY)) || DEFAULT_POWER_LEVEL;
  });
  const [cmdPathError, setCmdPathError] = useState(null);

  // Eager check on blur: the same rules the server applies to aiCmdPath at
  // start time, so a bad override (a shell function, a typo, a binary off
  // PATH) is flagged here instead of failing the next evaluation. A check
  // that cannot be reached stays silent — the start-time validation still
  // guards, and a transport hiccup must not brand a good value invalid.
  function validateCmdPath() {
    const value = state['cmd-path'];
    if (!value || value === providerId) {
      setCmdPathError(null);
      return;
    }
    api
      .checkCmdPath(providerId, value)
      .then((result) => setCmdPathError(result.ok ? null : result.error))
      .catch(() => setCmdPathError(null));
  }

  function persistPower(level) {
    setPower(level);
    writeString(POWER_KEY, String(level));
  }

  const hint = MODEL_HINTS[providerId];
  const analysisHint = ANALYSIS_MODEL_HINTS[providerId];

  const clampSubagents = (raw) => {
    const n = parseInt(raw, 10);
    if (Number.isNaN(n)) return String(DEFAULT_SUBAGENTS);
    return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
  };

  return { power, setPower, cmdPathError, validateCmdPath, persistPower, hint, analysisHint, clampSubagents };
}
