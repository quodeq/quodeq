import { useApi } from '../../../api/ApiContext.jsx';
import { LocalApiTabLayout, LocalApiModelRow, ModelPickerSelect } from './LocalApiTabLayout.jsx';
import { useOllamaModels } from '../hooks/useOllamaModels.js';
import { useLocalApiTabTest } from '../hooks/useLocalApiTabTest.js';
import { useOllamaLog } from '../ollama-log/OllamaLogContext.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

const OLLAMA_MODEL_HINT = tRich('settings.ollamaModelHint');

function ModelSelector({ value, models, onChange, labelId }) {
  const needsModel = !value;
  return (
    <div className="settings-model-field">
      <ModelPickerSelect
        className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`}
        value={value}
        models={models}
        onChange={onChange}
        labelId={labelId}
      />
      {needsModel && <span className="settings-model-hint">{t('settings.needModelBeforeEval')}</span>}
    </div>
  );
}

export default function OllamaTab({ state, update }) {
  const { testOllamaConcurrency } = useApi();
  const ollamaLog = useOllamaLog();
  const { ollamaStatus, models, modelsError } = useOllamaModels();

  const concurrency = useLocalApiTabTest({
    probe: () => testOllamaConcurrency(state.model).catch((err) => {
      console.warn('Ollama concurrency test failed', err);
      throw err;
    }),
    errorKey: 'settings.concurrencyTestFailedOllama',
    update,
    enabled: !!state.model,
  });

  return (
    <LocalApiTabLayout
      serverStatus={ollamaStatus}
      offlineMessage={<span>{tRich('settings.ollamaOffline')}</span>}
      onToggleConsole={() => (ollamaLog.open ? ollamaLog.closeLog() : ollamaLog.openLog())}
      consoleOpen={ollamaLog.open}
      modelsError={modelsError}
      modelRow={(
        <LocalApiModelRow
          hint={OLLAMA_MODEL_HINT}
          renderControl={(labelId) => (
            <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} labelId={labelId} />
          )}
        />
      )}
      state={state}
      update={update}
      subagentsDescription={t('settings.ollamaSubagentsDesc')}
      testDisabled={concurrency.testing || !state.model}
      concurrency={concurrency}
    />
  );
}
