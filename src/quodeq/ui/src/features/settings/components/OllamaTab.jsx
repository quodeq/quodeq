import { useApi } from '../../../api/ApiContext.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useOllamaModels } from '../hooks/useOllamaModels.js';
import { useLocalApiConcurrencyTest } from '../hooks/useLocalApiConcurrencyTest.js';
import { TimeLimitSetting } from './ProviderSettings.jsx';
import { LocalApiAdvancedPanel } from './LocalApiAdvancedPanel.jsx';
import { useOllamaLog } from '../ollama-log/OllamaLogContext.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const OLLAMA_MODEL_HINT = tRich('settings.ollamaModelHint');

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

function OllamaModelRow({ state, models, update }) {
  return (
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
  );
}

export default function OllamaTab({ state, update }) {
  const { testOllamaConcurrency } = useApi();
  const ollamaLog = useOllamaLog();
  const { ollamaStatus, models, modelsError } = useOllamaModels();

  const { testing, testResult, testError: rawTestError, runTest: runConcurrencyTest } = useLocalApiConcurrencyTest(
    () => testOllamaConcurrency(state.model).catch((err) => {
      console.warn('Ollama concurrency test failed', err);
      throw err;
    }),
  );
  const testError = rawTestError ? t('settings.concurrencyTestFailedOllama') : null;
  const runTest = async () => {
    if (!state.model) return;
    const result = await runConcurrencyTest();
    if (result?.recommended) update('subagents', String(result.recommended));
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
      <OllamaModelRow state={state} models={models} update={update} />
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <LocalApiAdvancedPanel
        subagentsDescription={t('settings.ollamaSubagentsDesc')}
        state={state}
        update={update}
        testing={testing}
        testDisabled={testing || !state.model}
        onRunTest={runTest}
        testResult={testResult}
        testError={testError}
      />
    </>
  );
}
