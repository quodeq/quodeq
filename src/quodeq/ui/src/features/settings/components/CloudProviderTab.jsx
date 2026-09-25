import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, PROVIDER_SETTING_KEY } from '../../../constants.js';
import { TimeLimitSetting, AdvancedAnalysisSettings } from './ProviderSettings.jsx';
import { SettingsRowLabel, RemoteSubagentsRow, SettingsAdvanced } from './settingsRowParts.jsx';
import { clampSubagentsTo } from './localApiSubagents.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';
import { PROVIDER_CLASSIFICATION } from './providerUtils.js';

// A cloud tab falls back to the minimum when the entry is unusable.
const clampCloudSubagents = (raw) => clampSubagentsTo(raw, String(MIN_SUBAGENTS));

const CLOUD_MODEL_HINTS = {
  openrouter: tRich('settings.cloudModelHintOpenrouter'),
  custom: tRich('settings.cloudModelHintCustom'),
};

function ModelRow({ hint, browseUrl, state, update, testing, testResult, runTest }) {
  return (
    <div className="settings-row">
      <SettingsRowLabel
        label={t('settings.modelLabel')}
        hint={hint}
        hintAria={t('settings.modelHelpAria')}
        description={<>
          {t('settings.typeModelIdDesc')}
          {browseUrl && <> <a href={browseUrl} target="_blank" rel="noopener noreferrer">{t('settings.browseModels')}</a></>}
        </>}
      />
      <div className="settings-budget-control">
        <input
          type="text"
          className={`settings-model-input${!state.model ? ' settings-model-input--required' : ''}`}
          value={state.model || ''}
          placeholder={t('settings.typeModelId')}
          onChange={(e) => update(PROVIDER_SETTING_KEY.MODEL, e.target.value)}
          aria-label={t('settings.modelIdentifierAria')}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
        />
        <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !state.model}>
          {testing ? t('settings.testing') : t('settings.test')}
        </button>
      </div>
      {!state.model && <span className="settings-model-hint">{t('settings.needModelBeforeEval')}</span>}
      {testResult && (
        <span className={`settings-description ${testResult.success ? '' : 'settings-error'}`}>
          {testResult.success ? t('settings.connected', { latency: testResult.latency_ms }) : testResult.error}
        </span>
      )}
    </div>
  );
}

export default function CloudProviderTab({ providerId, providerConfig, state, update }) {
  const { testProviderConnection } = useApi();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const browseUrl = providerConfig?.browse_url || '';
  const hint = CLOUD_MODEL_HINTS[providerId];

  const runTest = async () => {
    setTesting(true);
    try {
      const result = await testProviderConnection({
        provider: providerId,
        apiBase: providerConfig?.api_base || '',
        model: state.model,
        apiKey: '',
      });
      setTestResult(result);
    } catch (err) {
      console.warn('[CloudProviderTab] connection test failed:', err);
      setTestResult({ success: false, error: t('settings.connectionFailed') });
    }
    setTesting(false);
  };

  return (
    <>
      <ModelRow hint={hint} browseUrl={browseUrl} state={state} update={update} testing={testing} testResult={testResult} runTest={runTest} />
      <TimeLimitSetting state={state} update={update} providerType={PROVIDER_CLASSIFICATION.CLOUD_API} />
      <RemoteSubagentsRow state={state} update={update} clampSubagents={clampCloudSubagents} />
      <SettingsAdvanced>
        <AdvancedAnalysisSettings state={state} update={update} />
      </SettingsAdvanced>
    </>
  );
}
