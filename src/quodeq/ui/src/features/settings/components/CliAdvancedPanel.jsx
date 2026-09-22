import HelpHint from '../../../components/HelpHint.jsx';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { AdvancedAnalysisSettings } from './ProviderSettings.jsx';
import { t } from '../../../strings/index.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import CopilotModelSelect from './CopilotModelSelect.jsx';

// The three analysis tiers, in the order the panel lists them: the settings
// field each writes and the key of the label beside its input.
const ANALYSIS_TIERS = [
  { field: 'model-fast', labelKey: 'settings.fast' },
  { field: 'model-balanced', labelKey: 'settings.balanced' },
  { field: 'model-thorough', labelKey: 'settings.thorough' },
];

// The one CLI provider whose models come from a live account lookup instead
// of a free-text field.
const COPILOT_PROVIDER_ID = 'copilot';

/** Use live model choices for Copilot without changing other CLI providers. */
export function CliModelInput({ providerId, ...props }) {
  return providerId === COPILOT_PROVIDER_ID ? <CopilotModelSelect {...props} /> : <ModelTextInput {...props} />;
}

export function ModelTextInput({ label, value, placeholder, onChange, required, ariaLabel }) {
  const inputId = `model-input-${label || 'default'}`;
  return (
    <div className="settings-model-field">
      {label && <label className="settings-model-label" htmlFor={inputId}>{label}</label>}
      <input
        type="text"
        id={inputId}
        className={`settings-model-input${required && !value ? ' settings-model-input--required' : ''}`}
        value={value || ''}
        placeholder={placeholder || t('settings.typeModelId')}
        onChange={(e) => onChange(e.target.value)}
        aria-label={ariaLabel || (label ? t('settings.modelNameAria', { label }) : t('settings.modelAria'))}
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
      />
    </div>
  );
}

function AnalysisModelsRow({ providerId, state, update, analysisHint }) {
  const placeholder = providerId === COPILOT_PROVIDER_ID ? t('settings.copilotInheritModel') : undefined;
  return (
    <div className="settings-row">
      <SettingsRowLabel
        label={t('settings.analysisModels')}
        hint={analysisHint}
        hintAria={t('settings.analysisModelsHelpAria')}
        description={t('settings.analysisModelsDesc')}
      />
      <div className="settings-model-overrides">
        {ANALYSIS_TIERS.map(({ field, labelKey }) => (
          <CliModelInput
            key={field}
            providerId={providerId}
            placeholder={placeholder}
            label={t(labelKey)}
            value={state[field]}
            onChange={(v) => update(field, v)}
          />
        ))}
      </div>
    </div>
  );
}

function AnalysisPowerRow({ power, setPower, persistPower }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">{t('settings.analysisPower')}</span>
        <span className="settings-description">{t('settings.analysisPowerDesc')}</span>
      </div>
      <PowerSelector value={power} onChange={setPower} onPersist={persistPower} />
    </div>
  );
}

function CmdOverrideRow({ providerId, state, update, cmdPathError, validateCmdPath }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label">{t('settings.cmdOverride')}</span>
          <HelpHint label={t('settings.cmdOverrideHelpAria')}>
            {t('settings.cmdOverrideHint', { provider: providerId })}
          </HelpHint>
        </span>
        <span className="settings-description">{t('settings.cmdOverrideDesc', { provider: providerId })}</span>
      </div>
      <div className="settings-model-field">
        <input
          type="text"
          className="settings-model-input"
          value={state['cmd-path'] || ''}
          placeholder={providerId}
          onChange={(e) => update('cmd-path', e.target.value.trim())}
          onBlur={validateCmdPath}
          aria-label={t('settings.cmdOverride')}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
        />
        {cmdPathError && (
          <span className="settings-model-hint settings-error" role="alert">
            {cmdPathError}
          </span>
        )}
      </div>
    </div>
  );
}

/**
 * CliProviderTab.jsx's `<details>` advanced-settings panel (analysis model
 * overrides, analysis power, cmd-path override). Extracted verbatim.
 */
export function CliAdvancedPanel({
  providerId, state, update, analysisHint, power, setPower, persistPower, cmdPathError, validateCmdPath,
}) {
  return (
    <details className="settings-advanced">
      <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
      <div className="settings-advanced-content">
        <AnalysisModelsRow providerId={providerId} state={state} update={update} analysisHint={analysisHint} />
        <AnalysisPowerRow power={power} setPower={setPower} persistPower={persistPower} />
        <CmdOverrideRow providerId={providerId} state={state} update={update} cmdPathError={cmdPathError} validateCmdPath={validateCmdPath} />
        <AdvancedAnalysisSettings state={state} update={update} />
      </div>
    </details>
  );
}
