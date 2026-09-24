import { TimeLimitSetting } from './ProviderSettings.jsx';
import { SettingsRowLabel, RemoteSubagentsRow } from './settingsRowParts.jsx';
import { CliAdvancedPanel, CliModelInput } from './CliAdvancedPanel.jsx';
import { useCliProviderTab } from '../hooks/useCliProviderTab.js';
import { t } from '../../../strings/index.js';
import { CopilotModelStatus } from './CopilotModelSelect.jsx';
import { PROVIDER } from '../../../vocab/provider.js';
import { PROVIDER_CLASSIFICATION } from './providerUtils.js';
import { PROVIDER_SETTING_KEY } from '../../../constants.js';

export default function CliProviderTab({ providerId, state, update }) {
  const {
    power, setPower, cmdPathError, validateCmdPath, persistPower, hint, analysisHint, clampSubagents,
  } = useCliProviderTab({ providerId, state });

  return (
    <>
      {providerId === PROVIDER.COPILOT && <CopilotModelStatus />}
      <div className="settings-row">
        <SettingsRowLabel
          label={t('settings.modelLabel')}
          hint={hint}
          hintAria={t('settings.modelHelpAria')}
          description={t('settings.pickModelYouWant')}
        />
        <div className="settings-model-field">
          <CliModelInput providerId={providerId} value={state.model} onChange={(v) => update(PROVIDER_SETTING_KEY.MODEL, v)} required />
          {!state.model && <span className="settings-model-hint">{t('settings.pickModelToStart')}</span>}
        </div>
      </div>
      <TimeLimitSetting state={state} update={update} providerType={PROVIDER_CLASSIFICATION.CLI} />
      <RemoteSubagentsRow state={state} update={update} clampSubagents={clampSubagents} />
      <CliAdvancedPanel
        providerId={providerId} state={state} update={update} analysisHint={analysisHint}
        power={power} setPower={setPower} persistPower={persistPower}
        cmdPathError={cmdPathError} validateCmdPath={validateCmdPath}
      />
    </>
  );
}
