import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { AdvancedAnalysisSettings, SUBAGENTS_HINT_OLLAMA } from './ProviderSettings.jsx';
import { clampSubagents } from './localApiSubagents.js';
import { t } from '../../../strings/index.js';

/**
 * Shared `<details>` advanced-settings panel for the local-API tabs
 * (Omlx/LlamaCpp/Ollama): max-parallel-agents input + auto-detect button +
 * test result/error, plus AdvancedAnalysisSettings. Was duplicated (with
 * only the subagents description and the auto-detect button's disabled
 * condition differing per provider) before this extraction.
 */
export function LocalApiAdvancedPanel({
  subagentsDescription, state, update, testing, testDisabled, onRunTest, testResult, testError,
  subagentsAriaLabel,
}) {
  return (
    <details className="settings-advanced">
      <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
      <div className="settings-advanced-content">
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label-row">
              <span className="settings-label">{t('settings.maxParallelAgents')}</span>
              <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_OLLAMA}</HelpHint>
            </span>
            <span className="settings-description">{subagentsDescription}</span>
          </div>
          <div className="settings-budget-control">
            <input
              type="number"
              aria-label={subagentsAriaLabel}
              className="settings-model-input"
              min={MIN_SUBAGENTS}
              max={MAX_SUBAGENTS}
              value={state.subagents}
              onChange={(e) => update('subagents', e.target.value)}
              onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
            />
            <button type="button" className="settings-action-btn" onClick={onRunTest} disabled={testDisabled}>
              {testing ? t('settings.testing') : t('settings.autoDetect')}
            </button>
          </div>
          {testResult && <span className="settings-description">{t('settings.recommendedAgents', { count: testResult.recommended })}</span>}
          {testError && <span className="settings-error">{testError}</span>}
        </div>
        <AdvancedAnalysisSettings state={state} update={update} />
      </div>
    </details>
  );
}
