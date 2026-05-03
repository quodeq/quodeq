import { useState } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_REMOTE } from './ProviderSettings.jsx';

const CLOUD_MODEL_HINTS = {
  openrouter: (
    <>
      Type the model id you want. From cheapest to most expensive, you might try <code>meta-llama/llama-3.1-8b-instruct:free</code>, <code>anthropic/claude-haiku-4-5</code>, <code>anthropic/claude-sonnet-4</code>, or <code>anthropic/claude-opus-4-7</code>. The full catalog is on OpenRouter.
    </>
  ),
  custom: (
    <>
      Type the model id your API expects.
    </>
  ),
};

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
        apiBase: providerConfig?.api_base || '',
        model: state.model,
        apiKey: '',
      });
      setTestResult(result);
    } catch { setTestResult({ success: false, error: 'Connection failed' }); }
    setTesting(false);
  };

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Model</span>
            {hint && <HelpHint label="Model help">{hint}</HelpHint>}
          </span>
          <span className="settings-description">
            Type the model id you want to use.
            {browseUrl && <> <a href={browseUrl} target="_blank" rel="noopener noreferrer">Browse models</a></>}
          </span>
        </div>
        <div className="settings-budget-control">
          <input
            type="text"
            className={`settings-model-input${!state.model ? ' settings-model-input--required' : ''}`}
            value={state.model || ''}
            placeholder="Type model id"
            onChange={(e) => update('model', e.target.value)}
            aria-label="Model identifier"
          />
          <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !state.model}>
            {testing ? 'Testing...' : 'Test'}
          </button>
        </div>
        {!state.model && <span className="settings-model-hint">You&apos;ll need a model before you can run an evaluation.</span>}
        {testResult && (
          <span className={`settings-description ${testResult.success ? '' : 'settings-error'}`}>
            {testResult.success ? `Connected (${testResult.latency_ms}ms)` : testResult.error}
          </span>
        )}
      </div>
      <TimeLimitSetting state={state} update={update} providerType="cloud-api" />
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Max parallel agents</span>
            <HelpHint label="Max parallel agents help">{SUBAGENTS_HINT_REMOTE}</HelpHint>
          </span>
          <span className="settings-description">How many subagents work side by side. Pick a number from 1 to 10.</span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_SUBAGENTS}
          max={MAX_SUBAGENTS}
          value={state.subagents ?? ''}
          onChange={(e) => update('subagents', e.target.value)}
          onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
          aria-label="Max parallel agents"
        />
      </div>
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">Advanced</summary>
        <div className="settings-advanced-content">
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
