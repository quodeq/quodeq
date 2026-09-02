import { useApi } from '../../../api/ApiContext.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useLlamaCppModels } from '../hooks/useLlamaCppModels.js';
import { useLocalApiConcurrencyTest } from '../hooks/useLocalApiConcurrencyTest.js';
import { TimeLimitSetting } from './ProviderSettings.jsx';
import { LocalApiAdvancedPanel } from './LocalApiAdvancedPanel.jsx';
import { useLlamaCppLog } from '../llamacpp-log/LlamaCppLogContext.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const LLAMACPP_MODEL_HINT = (
  <>
    <p>{tRich('settings.llamacppModelHintP1')}</p>
    <p>{tRich('settings.llamacppModelHintP2')}</p>
  </>
);

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

function LlamaCppModelRow({ models }) {
  return (
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
  );
}

export default function LlamaCppTab({ state, update }) {
  const { testLlamacppConcurrency } = useApi();
  const llamacppLog = useLlamaCppLog();
  const { llamacppStatus, models, modelsError } = useLlamaCppModels({ state, update });

  const { testing, testResult, testError: rawTestError, runTest: runConcurrencyTest } = useLocalApiConcurrencyTest(
    () => testLlamacppConcurrency(state.model || (models[0]?.name ?? '')).catch((err) => {
      console.warn('llama.cpp concurrency test failed', err);
      throw err;
    }),
  );
  const testError = rawTestError ? t('settings.concurrencyTestFailedLlamacpp') : null;
  const runTest = async () => {
    const result = await runConcurrencyTest();
    if (result?.recommended) update('subagents', String(result.recommended));
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
      <LlamaCppModelRow models={models} />
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <LocalApiAdvancedPanel
        subagentsDescription={t('settings.llamacppSubagentsDesc')}
        subagentsAriaLabel={t('settings.maxParallelAgents')}
        state={state}
        update={update}
        testing={testing}
        testDisabled={testing || !models.length}
        onRunTest={runTest}
        testResult={testResult}
        testError={testError}
      />
    </>
  );
}
