import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useOmlxServerStatus } from '../hooks/useOmlxServerStatus.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_OLLAMA } from './ProviderSettings.jsx';

const OMLX_MODEL_HINT = (
  <>
    This list comes from your local omlx server. To add a model, use the omlx admin UI at{' '}
    <code>http://localhost:8000/admin</code> or pull a model with the omlx CLI. Models show up here as soon as they are downloaded.
  </>
);

function ModelSelector({ value, models, onChange }) {
  const needsModel = !value;
  const hasModels = models.length > 0;
  return (
    <div className="settings-model-field">
      {hasModels ? (
        <select
          className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Pick a model</option>
          {models.map((m) => (
            <option key={m.name} value={m.name}>{m.name}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`}
          placeholder="mlx-community/gemma-3-4b-it-4bit"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {needsModel && (
        <span className="settings-model-hint">
          {hasModels
            ? "You'll need a model before you can run an evaluation."
            : "omlx didn't return any models. Enter the model name directly (e.g. from your omlx admin UI)."}
        </span>
      )}
    </div>
  );
}

export default function OmlxTab({ state, update }) {
  const { getOmlxModels, testOmlxConcurrency } = useApi();
  const apiBase = state['api-base'] || '';
  const apiKey = state['api-key'] || '';
  const omlxStatus = useOmlxServerStatus(apiBase || undefined);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: ['settings', 'omlxModels', apiBase, apiKey],
    queryFn: () => getOmlxModels(apiBase || undefined, apiKey || undefined),
  });
  const modelsError = modelsQueryError
    ? "We couldn’t load your omlx models. Make sure omlx is running."
    : null;

  const prevStatusRef = useRef(omlxStatus?.status ?? 'offline');
  useEffect(() => {
    const status = omlxStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: ['settings', 'omlxModels'] });
    }
    prevStatusRef.current = status;
  }, [omlxStatus?.status, queryClient]);

  const runTest = async () => {
    if (!state.model) return;
    setTesting(true);
    try {
      const result = await testOmlxConcurrency(state.model, apiBase || undefined, apiKey || undefined);
      setTestResult(result);
      if (result.recommended) update('subagents', String(result.recommended));
    } catch (err) {
      console.warn('omlx concurrency test failed', err);
      setTestResult(null);
      setTestError("The concurrency test didn't finish. Make sure omlx is running and your model is loaded.");
    }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={omlxStatus?.status ?? 'offline'}
        address={omlxStatus?.address}
        offlineMessage={
          <span>
            omlx isn&apos;t running. Start it with <code>omlx serve</code>, or open the omlx menu bar app.
          </span>
        }
      />
      {modelsError && (
        <div className="settings-row">
          <span className="settings-error">We couldn&apos;t load your omlx models. Make sure omlx is running.</span>
        </div>
      )}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Server address</span>
          <span className="settings-description">Leave blank to use the default (<code>http://localhost:8000</code>).</span>
        </div>
        <input
          type="text"
          className="settings-model-input"
          placeholder="http://localhost:8000"
          value={apiBase}
          onChange={(e) => update('api-base', e.target.value)}
        />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">API key</span>
          <span className="settings-description">Leave blank to use the key from <code>~/.omlx/settings.json</code>.</span>
        </div>
        <input
          type="password"
          className="settings-model-input"
          placeholder="sk-..."
          value={apiKey}
          onChange={(e) => update('api-key', e.target.value)}
        />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Model</span>
            <HelpHint label="Model help">{OMLX_MODEL_HINT}</HelpHint>
          </span>
          <span className="settings-description">This model handles every step of your evaluation.</span>
        </div>
        <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} />
      </div>
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">Advanced</summary>
        <div className="settings-advanced-content">
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label-row">
                <span className="settings-label">Max parallel agents</span>
                <HelpHint label="Max parallel agents help">{SUBAGENTS_HINT_OLLAMA}</HelpHint>
              </span>
              <span className="settings-description">We make a guess based on your unified memory. Run a quick test for a more accurate number.</span>
            </div>
            <div className="settings-budget-control">
              <input
                type="number"
                className="settings-model-input"
                min={MIN_SUBAGENTS}
                max={MAX_SUBAGENTS}
                value={state.subagents}
                onChange={(e) => update('subagents', e.target.value)}
              />
              <button
                type="button"
                className="settings-action-btn"
                onClick={runTest}
                disabled={testing || !state.model}
              >
                {testing ? 'Testing...' : 'Auto-detect'}
              </button>
            </div>
            {testResult && <span className="settings-description">Recommended: {testResult.recommended} agents</span>}
            {testError && <span className="settings-error">{testError}</span>}
          </div>
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
