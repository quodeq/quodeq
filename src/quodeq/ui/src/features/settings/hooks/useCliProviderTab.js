import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { DEFAULT_MAX_SUBAGENTS, PROVIDER_SETTING_KEY } from '../../../constants.js';
import { clampSubagentsTo } from '../components/localApiSubagents.js';
import { tRich } from '../../../strings/rich.jsx';

const MODEL_HINTS = {
  claude: tRich('settings.modelHintClaude'),
  codex: tRich('settings.modelHintCodex'),
  gemini: tRich('settings.modelHintGemini'),
  agy: tRich('settings.modelHintAgy'),
  copilot: tRich('settings.modelHintCopilot'),
};

/**
 * Cmd-path validation, model hint and subagent clamping for one CLI
 * provider's settings tab.
 * @param {object} args
 * @param {string} args.providerId - picks the model-hint copy and is the
 *   baseline the cmd-path override is compared against.
 * @param {object} args.state - the tab's live draft; only `cmd-path` is read.
 * @returns {object} `cmdPathError`/`validateCmdPath` for the blur check,
 *   `hint` for the provider's model copy, and `clampSubagents`.
 */
export function useCliProviderTab({ providerId, state }) {
  const api = useApi();
  const [cmdPathError, setCmdPathError] = useState(null);

  // Eager check on blur: the same rules the server applies to aiCmdPath at
  // start time, so a bad override (a shell function, a typo, a binary off
  // PATH) is flagged here instead of failing the next evaluation. A check
  // that cannot be reached stays silent — the start-time validation still
  // guards, and a transport hiccup must not brand a good value invalid.
  function validateCmdPath() {
    const value = state[PROVIDER_SETTING_KEY.CMD_PATH];
    if (!value || value === providerId) {
      setCmdPathError(null);
      return;
    }
    api
      .checkCmdPath(providerId, value)
      .then((result) => setCmdPathError(result.ok ? null : result.error))
      .catch(() => setCmdPathError(null));
  }

  const hint = MODEL_HINTS[providerId];

  const clampSubagents = (raw) => clampSubagentsTo(raw, String(DEFAULT_MAX_SUBAGENTS));

  return { cmdPathError, validateCmdPath, hint, clampSubagents };
}
