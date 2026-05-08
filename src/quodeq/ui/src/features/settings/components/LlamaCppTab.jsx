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

const LLAMACPP_MODEL_HINT = (
  <>
    <p>llama-server runs one model at a time, fixed at launch by the <code>-m</code> flag. Whatever you started it with is what shows up here.</p>
    <p>To switch models, stop llama-server and relaunch it with a different GGUF file. For speculative decoding (MTP), pair the target model with a smaller drafter via <code>--model-draft</code>.</p>
  </>
);

function LoadedModel({ models }) {
  if (!models.length) {
    return <span className="settings-model-hint">No model loaded yet. Start llama-server with a GGUF file.</span>;
  }
  return (
    <div className="settings-model-field">
      <input className="settings-model-input" value={models[0].name} readOnly aria-label="Loaded model" />
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
    ? 'We couldn’t reach llama-server. Make sure it is running on port 8080.'
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
      setTestError('The concurrency test didn’t finish. Make sure llama-server is running.');
    }
    setTesting(false);
  };

  return (
    <>
      <ServerStatusPill
        status={llamacppStatus?.status ?? 'offline'}
        address={llamacppStatus?.address}
        offlineMessage={
          <span>
            llama-server isn&apos;t running. Start it with <code>llama-server -m model.gguf --port 8080</code>.
          </span>
        }
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
            <span className="settings-label">Loaded model</span>
            <HelpHint label="Loaded model help">{LLAMACPP_MODEL_HINT}</HelpHint>
          </span>
          <span className="settings-description">The GGUF currently loaded by llama-server.</span>
        </div>
        <LoadedModel models={models} />
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
              <span className="settings-description">Estimated from your VRAM. Run a quick test for a more accurate number.</span>
            </div>
            <div className="settings-budget-control">
              <input type="number" className="settings-model-input" min={MIN_SUBAGENTS} max={MAX_SUBAGENTS} value={state.subagents} onChange={(e) => update('subagents', e.target.value)} />
              <button type="button" className="settings-action-btn" onClick={runTest} disabled={testing || !models.length}>
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
