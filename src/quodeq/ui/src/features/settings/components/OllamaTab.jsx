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

const OLLAMA_MODEL_HINT = (
  <>
    This list comes straight from your local Ollama server. To add a model, download it with Ollama itself (for example, <code>ollama pull gemma4:26b</code>). As soon as the download finishes, it shows up here.
  </>
);

function ModelSelector({ value, models, onChange }) {
  const needsModel = !value;
  return (
    <div className="settings-model-field">
      <select className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Pick a model</option>
        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
      {needsModel && <span className="settings-model-hint">You&apos;ll need a model before you can run an evaluation.</span>}
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
    ? 'We couldn’t load your Ollama models. Make sure Ollama is running.'
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
    } catch (err) { console.warn('Ollama concurrency test failed', err); setTestResult(null); setTestError('The concurrency test didn’t finish. Make sure Ollama is running and your model is loaded.'); }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={ollamaStatus?.status ?? 'offline'}
        address={ollamaStatus?.address}
        offlineMessage={
          <span>
            Ollama isn&apos;t running. Start it with <code>ollama serve</code>, or open the Ollama app.
          </span>
        }
        onToggleConsole={() => (ollamaLog.open ? ollamaLog.closeLog() : ollamaLog.openLog())}
        consoleOpen={ollamaLog.open}
      />
      {modelsError && <div className="settings-row"><span className="settings-error">We couldn&apos;t load your Ollama models. Make sure Ollama is running.</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Model</span>
            <HelpHint label="Model help">{OLLAMA_MODEL_HINT}</HelpHint>
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
              <span className="settings-description">We make a guess based on your VRAM. Run a quick test for a more accurate number.</span>
            </div>
            <div className="settings-budget-control">
              <input type="number" className="settings-model-input" min={MIN_SUBAGENTS} max={MAX_SUBAGENTS} value={state.subagents} onChange={(e) => update('subagents', e.target.value)} />
              <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !state.model}>
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
