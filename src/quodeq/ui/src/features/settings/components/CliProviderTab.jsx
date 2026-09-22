import { TimeLimitSetting } from './ProviderSettings.jsx';
import { SettingsRowLabel, RemoteSubagentsRow } from './settingsRowParts.jsx';
import { CliAdvancedPanel, CliModelInput } from './CliAdvancedPanel.jsx';
import { useCliProviderTab } from '../hooks/useCliProviderTab.js';
import { t } from '../../../strings/index.js';
import { CopilotModelStatus } from './CopilotModelSelect.jsx';

export default function CliProviderTab({ providerId, state, update }) {
  const {
    power, setPower, cmdPathError, validateCmdPath, persistPower, hint, analysisHint, clampSubagents,
  } = useCliProviderTab({ providerId, state });

  return (
    <>
      {providerId === 'copilot' && <CopilotModelStatus />}
      <div className="settings-row">
        <SettingsRowLabel
          label={t('settings.modelLabel')}
          hint={hint}
          hintAria={t('settings.modelHelpAria')}
          description={t('settings.pickModelYouWant')}
        />
        <div className="settings-model-field">
          <CliModelInput providerId={providerId} value={state.model} onChange={(v) => update('model', v)} required />
          {!state.model && <span className="settings-model-hint">{t('settings.pickModelToStart')}</span>}
        </div>
      </div>
      <TimeLimitSetting state={state} update={update} providerType="cli" />
      <RemoteSubagentsRow state={state} update={update} clampSubagents={clampSubagents} />
      <CliAdvancedPanel
        providerId={providerId} state={state} update={update} analysisHint={analysisHint}
        power={power} setPower={setPower} persistPower={persistPower}
        cmdPathError={cmdPathError} validateCmdPath={validateCmdPath}
      />
    </>
  );
}
