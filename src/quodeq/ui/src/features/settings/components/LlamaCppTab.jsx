import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useLlamacppServerStatus } from '../hooks/useLlamacppServerStatus.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_OLLAMA } from './ProviderSettings.jsx';
import { useLlamaCppLog } from '../llamacpp-log/LlamaCppLogContext.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const LLAMACPP_MODEL_HINT = (
  <>
    <p>{tRich('settings.llamacppModelHintP1')}</p>
    <p>{tRich('settings.llamacppModelHintP2')}</p>
  </>
);


// Local-API tabs default to a single subagent; clamp commits to [MIN, MAX]
// so an empty/garbage entry can't persist to storage.
const LOCAL_DEFAULT_SUBAGENTS = '1';
function clampSubagents(raw) {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n)) return LOCAL_DEFAULT_SUBAGENTS;
  return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
}

function LoadedModel({ models }) {
  if (!models.length) {
    return <span className="settings-model-hint">{t('settings.llamacppNoModel')}</span>;
  }
  return (
    <div className="settings-model-field">
      <input className="settings-model-input" value={models[0].name} readOnly aria-label={t('settings.loadedModelAria')} />
    </div>
  );
}

export default function LlamaCppTab({ state, update }) {
  const { getLlamacppModels, testLlamacppConcurrency } = useApi();
  const llamacppStatus = useLlamacppServerStatus();
  const llamacppLog = useLlamaCppLog();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: settingsKeys.llamacppModels(),
    queryFn: () => getLlamacppModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.llamacppLoadFailed')
    : null;

  // When llama-server transitions offline -> online, refresh the models query
  // so the loaded model populates as soon as the status pill flips to green.
  const prevStatusRef = useRef(llamacppStatus?.status ?? 'offline');
  useEffect(() => {
    const status = llamacppStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: settingsKeys.llamacppModels() });
    }
    prevStatusRef.current = status;
  }, [llamacppStatus?.status, queryClient]);

  // The model name comes from llama-server itself. Mirror it into provider
  // state so the analysis runner has a model to send.
  useEffect(() => {
    if (models.length && models[0].name && state.model !== models[0].name) {
      update('model', models[0].name);
    }
  }, [models, state.model, update]);

  const runTest = async () => {
    setTesting(true);
    try {
      const result = await testLlamacppConcurrency(state.model || (models[0]?.name ?? ''));
      setTestResult(result);
      if (result.recommended) update('subagents', String(result.recommended));
    } catch (err) {
      console.warn('llama.cpp concurrency test failed', err);
      setTestResult(null);
      setTestError(t('settings.concurrencyTestFailedLlamacpp'));
    }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={llamacppStatus?.status ?? 'offline'}
        address={llamacppStatus?.address}
        offlineMessage={<span>{tRich('settings.llamacppOffline')}</span>}
        onToggleConsole={
          llamacppLog.available
            ? () => (llamacppLog.open ? llamacppLog.closeLog() : llamacppLog.openLog())
            : undefined
        }
        consoleOpen={llamacppLog.open}
      />
      {modelsError && <div className="settings-row"><span className="settings-error">{modelsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.loadedModel')}</span>
            <HelpHint label={t('settings.loadedModelHelpAria')}>{LLAMACPP_MODEL_HINT}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.loadedModelDesc')}</span>
        </div>
        <LoadedModel models={models} />
      </div>
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
        <div className="settings-advanced-content">
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label-row">
                <span className="settings-label">{t('settings.maxParallelAgents')}</span>
                <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_OLLAMA}</HelpHint>
              </span>
              <span className="settings-description">{t('settings.llamacppSubagentsDesc')}</span>
            </div>
            <div className="settings-budget-control">
              <input type="number" aria-label={t('settings.maxParallelAgents')} className="settings-model-input" min={MIN_SUBAGENTS} max={MAX_SUBAGENTS} value={state.subagents} onChange={(e) => update('subagents', e.target.value)} onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }} />
              <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !models.length}>
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
