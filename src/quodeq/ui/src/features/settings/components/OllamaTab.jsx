import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useOllamaServerStatus } from '../hooks/useOllamaServerStatus.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_OLLAMA } from './ProviderSettings.jsx';
import { useOllamaLog } from '../ollama-log/OllamaLogContext.js';
import { settingsKeys } from '../../../api/queryKeys.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const OLLAMA_MODEL_HINT = tRich('settings.ollamaModelHint');


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
  return (
    <div className="settings-model-field">
      <select className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t('settings.pickAModel')}</option>
        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
      {needsModel && <span className="settings-model-hint">{t('settings.needModelBeforeEval')}</span>}
    </div>
  );
}

export default function OllamaTab({ state, update }) {
  const { getOllamaModels, testOllamaConcurrency } = useApi();
  const ollamaLog = useOllamaLog();
  const ollamaStatus = useOllamaServerStatus();
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  const queryClient = useQueryClient();
  const { data: models = [], error: modelsQueryError } = useQuery({
    queryKey: settingsKeys.ollamaModels(),
    queryFn: () => getOllamaModels(),
  });
  const modelsError = modelsQueryError
    ? t('settings.ollamaModelsLoadFailed')
    : null;

  // When Ollama transitions offline → online, the cached models query is
  // either an empty list or a previous error — neither auto-refetches just
  // because the daemon came up. Invalidate it so the dropdown populates as
  // soon as the status pill flips to green, without requiring a navigation.
  const prevStatusRef = useRef(ollamaStatus?.status ?? 'offline');
  useEffect(() => {
    const status = ollamaStatus?.status ?? 'offline';
    if (prevStatusRef.current !== 'online' && status === 'online') {
      queryClient.invalidateQueries({ queryKey: settingsKeys.ollamaModels() });
    }
    prevStatusRef.current = status;
  }, [ollamaStatus?.status, queryClient]);

  const runTest = async () => {
    if (!state.model) return;
    setTesting(true);
    try {
      const result = await testOllamaConcurrency(state.model);
      setTestResult(result);
      if (result.recommended) update('subagents', String(result.recommended));
    } catch (err) { console.warn('Ollama concurrency test failed', err); setTestResult(null); setTestError(t('settings.concurrencyTestFailedOllama')); }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={ollamaStatus?.status ?? 'offline'}
        address={ollamaStatus?.address}
        offlineMessage={<span>{tRich('settings.ollamaOffline')}</span>}
        onToggleConsole={() => (ollamaLog.open ? ollamaLog.closeLog() : ollamaLog.openLog())}
        consoleOpen={ollamaLog.open}
      />
      {modelsError && <div className="settings-row"><span className="settings-error">{modelsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.modelLabel')}</span>
            <HelpHint label={t('settings.modelHelpAria')}>{OLLAMA_MODEL_HINT}</HelpHint>
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
              <span className="settings-label-row">
                <span className="settings-label">{t('settings.maxParallelAgents')}</span>
                <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_OLLAMA}</HelpHint>
              </span>
              <span className="settings-description">{t('settings.ollamaSubagentsDesc')}</span>
            </div>
            <div className="settings-budget-control">
              <input type="number" className="settings-model-input" min={MIN_SUBAGENTS} max={MAX_SUBAGENTS} value={state.subagents} onChange={(e) => update('subagents', e.target.value)} onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }} />
              <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !state.model}>
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
