import { useState } from 'react';
import { testProviderConnection } from '../../../api/index.js';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import { TimeLimitSetting, AdvancedAnalysisSettings } from './ProviderSettings.jsx';

export default function CloudProviderTab({ providerId, providerConfig, state, update }) {
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const browseUrl = providerConfig?.browse_url || '';

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
          <span className="settings-label">Model</span>
          <span className="settings-description">
            Enter the model identifier.
            {browseUrl && <> <a href={browseUrl} target="_blank" rel="noopener noreferrer">Browse models</a></>}
          </span>
        </div>
        <div className="settings-budget-control">
          <input
            type="text"
            className={`settings-model-input${!state.model ? ' settings-model-input--required' : ''}`}
            value={state.model}
            placeholder="e.g. qwen/qwen3.6-plus-preview:free"
            onChange={(e) => update('model', e.target.value)}
          />
          <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !state.model}>
            {testing ? 'Testing...' : 'Test'}
          </button>
        </div>
        {!state.model && <span className="settings-model-hint">Required before running an evaluation</span>}
        {testResult && (
          <span className={`settings-description ${testResult.success ? '' : 'settings-error'}`}>
            {testResult.success ? `Connected (${testResult.latency_ms}ms)` : testResult.error}
          </span>
        )}
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Max parallel agents</span>
          <span className="settings-description">Number of subagents to run in parallel (1–10)</span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_SUBAGENTS}
          max={MAX_SUBAGENTS}
          value={parseInt(state.subagents || '1', 10)}
          onBlur={(e) => update('subagents', Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, parseInt(e.target.value, 10) || 1)))}
          onChange={(e) => update('subagents', e.target.value)}
        />
      </div>
      <TimeLimitSetting state={state} update={update} />
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">Advanced</summary>
        <div className="settings-advanced-content">
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
