import { useApi } from '../../../api/ApiContext.jsx';
import { LocalApiTabLayout, LocalApiModelSelectRow, ModelPickerSelect } from './LocalApiTabLayout.jsx';
import { useOmlxModels } from '../hooks/useOmlxModels.js';
import { useLocalApiTabTest } from '../hooks/useLocalApiTabTest.js';
import { warnAndRethrow } from '../settingsHelpers.js';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';
import { PROVIDER_SETTING_KEY } from '../../../constants.js';

function ModelSelector({ value, models, onChange, labelId }) {
  const needsModel = !value;
  const hasModels = models.length > 0;
  const inputClass = `settings-model-input${needsModel ? ' settings-model-input--required' : ''}`;
  return (
    <div className="settings-model-field">
      {hasModels ? (
        <ModelPickerSelect
          className={inputClass}
          value={value}
          models={models}
          onChange={onChange}
          labelId={labelId}
        />
      ) : (
        <input
          type="text"
          className={inputClass}
          placeholder="mlx-community/gemma-3-4b-it-4bit"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-labelledby={labelId}
        />
      )}
      {needsModel && (
        <span className="settings-model-hint">
          {hasModels
            ? t('settings.needModelBeforeEval')
            : t('settings.omlxNoModels')}
        </span>
      )}
    </div>
  );
}

export default function OmlxTab({ state, update }) {
  const { testOmlxConcurrency } = useApi();
  const apiBase = state[PROVIDER_SETTING_KEY.API_BASE] || '';
  const apiKey = state[PROVIDER_SETTING_KEY.API_KEY] || '';
  const { omlxStatus, models, modelsError } = useOmlxModels({ apiBase, apiKey });

  const concurrency = useLocalApiTabTest({
    probe: warnAndRethrow(() => testOmlxConcurrency(state.model, apiBase || undefined, apiKey || undefined), 'omlx'),
    errorKey: 'settings.concurrencyTestFailedOmlx',
    update,
    enabled: !!state.model,
  });

  return (
    <LocalApiTabLayout
      serverStatus={omlxStatus}
      offlineMessage={<span>{tRich('settings.omlxOffline')}</span>}
      modelsError={modelsError}
      modelRow={<LocalApiModelSelectRow hint={tRich('settings.omlxModelHint')} Control={ModelSelector} state={state} update={update} models={models} />}
      state={state}
      update={update}
      subagentsDescription={t('settings.omlxSubagentsDesc')}
      testDisabled={concurrency.testing || !state.model}
      concurrency={concurrency}
    />
  );
}
