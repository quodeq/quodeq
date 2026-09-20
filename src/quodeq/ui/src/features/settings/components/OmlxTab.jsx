import { useId } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import { useOmlxModels } from '../hooks/useOmlxModels.js';
import { useLocalApiTabTest } from '../hooks/useLocalApiTabTest.js';
import { TimeLimitSetting } from './ProviderSettings.jsx';
import { LocalApiAdvancedPanel } from './LocalApiAdvancedPanel.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

function ModelSelector({ value, models, onChange, labelId }) {
  const needsModel = !value;
  const hasModels = models.length > 0;
  return (
    <div className="settings-model-field">
      {hasModels ? (
        <select
          className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-labelledby={labelId}
        >
          <option value="">{t('settings.pickAModel')}</option>
          {models.map((m) => (
            <option key={m.name} value={m.name}>{m.name}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          className={`settings-model-input${needsModel ? ' settings-model-input--required' : ''}`}
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

function OmlxModelRow({ state, models, update }) {
  const labelId = useId();
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label" id={labelId}>{t('settings.modelLabel')}</span>
          <HelpHint label={t('settings.modelHelpAria')}>{tRich('settings.omlxModelHint')}</HelpHint>
        </span>
        <span className="settings-description">{t('settings.thisModelEveryStep')}</span>
      </div>
      <ModelSelector value={state.model} models={models} onChange={(v) => update('model', v)} labelId={labelId} />
    </div>
  );
}

export default function OmlxTab({ state, update }) {
  const { testOmlxConcurrency } = useApi();
  const apiBase = state['api-base'] || '';
  const apiKey = state['api-key'] || '';
  const { omlxStatus, models, modelsError } = useOmlxModels({ apiBase, apiKey });

  const concurrency = useLocalApiTabTest({
    probe: () => testOmlxConcurrency(state.model, apiBase || undefined, apiKey || undefined),
    warnLabel: 'omlx concurrency test failed',
    errorKey: 'settings.concurrencyTestFailedOmlx',
    update,
    enabled: !!state.model,
  });

  return (
    <>
      <ServerStatusPill
        status={omlxStatus?.status ?? 'offline'}
        address={omlxStatus?.address}
        offlineMessage={<span>{tRich('settings.omlxOffline')}</span>}
      />
      {modelsError && (
        <div className="settings-row">
          <span className="settings-error">{modelsError}</span>
        </div>
      )}
      <OmlxModelRow state={state} models={models} update={update} />
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <LocalApiAdvancedPanel
        subagentsDescription={t('settings.omlxSubagentsDesc')}
        state={state}
        update={update}
        testDisabled={concurrency.testing || !state.model}
        {...concurrency}
      />
    </>
  );
}
