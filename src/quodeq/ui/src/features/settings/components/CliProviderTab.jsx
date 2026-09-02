import { MIN_SUBAGENTS, MAX_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { TimeLimitSetting, SUBAGENTS_HINT_REMOTE } from './ProviderSettings.jsx';
import { CliAdvancedPanel, ModelTextInput } from './CliAdvancedPanel.jsx';
import { useCliProviderTab } from '../hooks/useCliProviderTab.js';
import { t } from '../../../strings/index.js';

export default function CliProviderTab({ providerId, state, update }) {
  const {
    power, setPower, cmdPathError, validateCmdPath, persistPower, hint, analysisHint, clampSubagents,
  } = useCliProviderTab({ providerId, state });

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.modelLabel')}</span>
            {hint && <HelpHint label={t('settings.modelHelpAria')}>{hint}</HelpHint>}
          </span>
          <span className="settings-description">{t('settings.pickModelYouWant')}</span>
        </div>
        <div className="settings-model-field">
          <ModelTextInput value={state.model} onChange={(v) => update('model', v)} required />
          {!state.model && <span className="settings-model-hint">{t('settings.pickModelToStart')}</span>}
        </div>
      </div>
      <TimeLimitSetting state={state} update={update} providerType="cli" />
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.maxParallelAgents')}</span>
            <HelpHint label={t('settings.maxParallelAgentsHelpAria')}>{SUBAGENTS_HINT_REMOTE}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.subagentsDescRemote')}</span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_SUBAGENTS}
          max={MAX_SUBAGENTS}
          value={state.subagents ?? ''}
          onChange={(e) => update('subagents', e.target.value)}
          onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
          aria-label={t('settings.maxParallelAgents')}
        />
      </div>
      <CliAdvancedPanel
        providerId={providerId} state={state} update={update} analysisHint={analysisHint}
        power={power} setPower={setPower} persistPower={persistPower}
        cmdPathError={cmdPathError} validateCmdPath={validateCmdPath}
      />
    </>
  );
}
