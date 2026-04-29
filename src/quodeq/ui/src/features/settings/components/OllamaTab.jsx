import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import ServerStatus from './ServerStatus.jsx';
import { TimeLimitSetting, AdvancedAnalysisSettings } from './ProviderSettings.jsx';
import ConsoleButton from '../../../components/ConsoleButton.jsx';
import { useOllamaLog } from '../ollama-log/OllamaLogContext.js';

function ModelSelector({ value, models, onChange }) {
  const needsModel = !value;
  return (
    <div className="settings-model-field">
      <select className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a model</option>
        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
      {needsModel && <span className="settings-model-hint">Required before running an evaluation</span>}
    </div>
  );
}

export default function OllamaTab({ state, update }) {
  const { getOllamaModels, testOllamaConcurrency } = useApi();
  const ollamaLog = useOllamaLog();
  const [models, setModels] = useState([]);
  const [modelsError, setModelsError] = useState(null);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testError, setTestError] = useState(null);

  useEffect(() => {
    getOllamaModels()
      .then((data) => { setModels(data); setModelsError(null); })
      .catch(() => { setModels([]); setModelsError('Failed to load Ollama models. Check that Ollama is running.'); });
  }, []);

  const runTest = async () => {
    if (!state.model) return;
    setTesting(true);
    try {
      const result = await testOllamaConcurrency(state.model);
      setTestResult(result);
      if (result.recommended) update('subagents', String(result.recommended));
    } catch (err) { console.warn('Ollama concurrency test failed', err); setTestResult(null); setTestError('Concurrency test failed. Verify Ollama is running and the model is loaded.'); }
    setTesting(false);
  };

  return (
    <>
      <div className="settings-server-row">
        <ServerStatus />
        <ConsoleButton
          open={ollamaLog.open}
          onToggle={() => (ollamaLog.open ? ollamaLog.closeLog() : ollamaLog.openLog())}
        />
      </div>
      {modelsError && <div className="settings-row"><span className="settings-error">{modelsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">Model used for all evaluation phases</span>
        </div>
        <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Max parallel agents</span>
          <span className="settings-description">Auto-detected from VRAM. Test for accuracy.</span>
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
