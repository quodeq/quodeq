import { useApi } from '../../../api/ApiContext.jsx';
import { LocalApiTabLayout } from './LocalApiTabLayout.jsx';
import { useLlamaCppModels } from '../hooks/useLlamaCppModels.js';
import { useLocalApiTabTest } from '../hooks/useLocalApiTabTest.js';
import { useLlamaCppLog } from '../llamacpp-log/LlamaCppLogContext.js';
import { warnAndRethrow, toggleLogWindow } from '../settingsHelpers.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';
import { SettingsRowLabel } from './settingsRowParts.jsx';

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
      <SettingsRowLabel
        label={t('settings.loadedModel')}
        hint={LLAMACPP_MODEL_HINT}
        hintAria={t('settings.loadedModelHelpAria')}
        description={t('settings.loadedModelDesc')}
      />
      <LoadedModel models={models} />
    </div>
  );
}

export default function LlamaCppTab({ state, update }) {
  const { testLlamacppConcurrency } = useApi();
  const llamacppLog = useLlamaCppLog();
  const { llamacppStatus, models, modelsError } = useLlamaCppModels({ state, update });

  const concurrency = useLocalApiTabTest({
    probe: warnAndRethrow(() => testLlamacppConcurrency(state.model || (models[0]?.name ?? '')), 'llama.cpp'),
    errorKey: 'settings.concurrencyTestFailedLlamacpp',
    update,
  });

  return (
    <LocalApiTabLayout
      serverStatus={llamacppStatus}
      offlineMessage={<span>{tRich('settings.llamacppOffline')}</span>}
      onToggleConsole={
        llamacppLog.available
          ? () => toggleLogWindow(llamacppLog)
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
