import { useApi } from '../../../api/ApiContext.jsx';
import { LocalApiTabLayout } from './LocalApiTabLayout.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useLlamaCppModels } from '../hooks/useLlamaCppModels.js';
import { useLocalApiTabTest } from '../hooks/useLocalApiTabTest.js';
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

  const concurrency = useLocalApiTabTest({
    probe: () => testLlamacppConcurrency(state.model || (models[0]?.name ?? '')).catch((err) => {
      console.warn('llama.cpp concurrency test failed', err);
      throw err;
    }),
    errorKey: 'settings.concurrencyTestFailedLlamacpp',
    update,
  });

  return (
    <LocalApiTabLayout
      serverStatus={llamacppStatus}
      offlineMessage={<span>{tRich('settings.llamacppOffline')}</span>}
      onToggleConsole={
        llamacppLog.available
          ? () => (llamacppLog.open ? llamacppLog.closeLog() : llamacppLog.openLog())
          : undefined
      }
      consoleOpen={llamacppLog.open}
      modelsError={modelsError}
      modelRow={<LlamaCppModelRow models={models} />}
      state={state}
      update={update}
      subagentsDescription={t('settings.llamacppSubagentsDesc')}
      subagentsAriaLabel={t('settings.maxParallelAgents')}
      testDisabled={concurrency.testing || !models.length}
      concurrency={concurrency}
    />
  );
}
