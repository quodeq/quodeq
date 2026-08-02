import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useOmlxServerStatus } from '../hooks/useOmlxServerStatus.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_OLLAMA } from './ProviderSettings.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const OMLX_MODEL_HINT = tRich('settings.omlxModelHint');


// Local-API tabs default to a single subagent; clamp commits to [MIN, MAX]
// so an empty/garbage entry can't persist to storage.
const LOCAL_DEFAULT_SUBAGENTS = '1';
function clampSubagents(raw) {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) return LOCAL_DEFAULT_SUBAGENTS;
  return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
}

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
          <option value="">{t('settings.pickAModel')}</option>
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
            ? t('settings.needModelBeforeEval')
            : t('settings.omlxNoModels')}
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
    ? t('settings.omlxModelsLoadFailed')
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
      setTestError(t('settings.concurrencyTestFailedOmlx'));
    }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={omlxStatus?.status ?? 'offline'}
        address={omlxStatus?.address}
        offlineMessage={<span>{tRich('settings.omlxOffline')}</span>}
      />
      {modelsError && (
        <div className="settings-row">
          <span className="settings-error">{modelsError}</span>
        </div>
      )}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.modelLabel')}</span>
            <HelpHint label={t('settings.modelHelpAria')}>{OMLX_MODEL_HINT}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.thisModelEveryStep')}</span>
        </div>
        <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} />
      </div>
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
        <div className="settings-advanced-content">
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">{t('settings.serverAddress')}</span>
              <span className="settings-description">{tRich('settings.serverAddressDesc')}</span>
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
              <span className="settings-label">{t('settings.apiKey')}</span>
              <span className="settings-description">{tRich('settings.apiKeyDesc')}</span>
            </div>
            <input
              type="password"
              className="settings-model-input"
              placeholder="1234"
              value={apiKey}
              onChange={(e) => update('api-key', e.target.value)}
            />
          </div>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label-row">
                <span className="settings-label">{t('settings.maxParallelAgents')}</span>
                <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_OLLAMA}</HelpHint>
              </span>
              <span className="settings-description">{t('settings.omlxSubagentsDesc')}</span>
            </div>
            <div className="settings-budget-control">
              <input
                type="number"
                className="settings-model-input"
                min={MIN_SUBAGENTS}
                max={MAX_SUBAGENTS}
                value={state.subagents}
                onChange={(e) => update('subagents', e.target.value)}
                onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
              />
              <button
                type="button"
                className="settings-action-btn"
                onClick={runTest}
                disabled={testing || !state.model}
              >
                {testing ? t('settings.testing') : t('settings.autoDetect')}
              </button>
            </div>
            {testResult && <span className="settings-description">{t('settings.recommendedAgents', { count: testResult.recommended })}</span>}
            {testError && <span className="settings-error">{testError}</span>}
          </div>
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
