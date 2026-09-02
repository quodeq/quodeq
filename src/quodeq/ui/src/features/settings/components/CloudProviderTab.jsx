import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_REMOTE } from './ProviderSettings.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const CLOUD_MODEL_HINTS = {
  openrouter: tRich('settings.cloudModelHintOpenrouter'),
  custom: tRich('settings.cloudModelHintCustom'),
};

function ModelRow({ hint, browseUrl, state, update, testing, testResult, runTest }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label">{t('settings.modelLabel')}</span>
          {hint && <HelpHint label={t('settings.modelHelpAria')}>{hint}</HelpHint>}
        </span>
        <span className="settings-description">
          {t('settings.typeModelIdDesc')}
          {browseUrl && <> <a href={browseUrl} target="_blank" rel="noopener noreferrer">{t('settings.browseModels')}</a></>}
        </span>
      </div>
      <div className="settings-budget-control">
        <input
          type="text"
          className={`settings-model-input${!state.model ? ' settings-model-input--required' : ''}`}
          value={state.model || ''}
          placeholder={t('settings.typeModelId')}
          onChange={(e) => update('model', e.target.value)}
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

function SubagentsRow({ state, update, clampSubagents }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label">{t('settings.maxParallelAgents')}</span>
          <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_REMOTE}</HelpHint>
        </span>
        <span className="settings-description">{t('settings.subagentsDescRemote')}</span>
      </div>
      <input
        type="number"
        className="settings-model-input"
        min={MIN_SUBAGENTS}
        max={MAX_SUBAGENTS}
        value={state.subagents ?? ''}
        onChange={(e) => update('subagents', e.target.value)}
        onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
        aria-label={t('settings.maxParallelAgents')}
      />
    </div>
  );
}

export default function CloudProviderTab({ providerId, providerConfig, state, update }) {
  const { testProviderConnection } = useApi();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const browseUrl = providerConfig?.browse_url || '';
  const hint = CLOUD_MODEL_HINTS[providerId];

  const clampSubagents = (raw) => {
    const n = parseInt(raw, 10);
    if (Number.isNaN(n)) return '1';
    return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
  };

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
    } catch { setTestResult({ success: false, error: t('settings.connectionFailed') }); }
    setTesting(false);
  };

  return (
    <>
      <ModelRow hint={hint} browseUrl={browseUrl} state={state} update={update} testing={testing} testResult={testResult} runTest={runTest} />
      <TimeLimitSetting state={state} update={update} providerType="cloud-api" />
      <SubagentsRow state={state} update={update} clampSubagents={clampSubagents} />
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
        <div className="settings-advanced-content">
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
