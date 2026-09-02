import HelpHint from '../../../components/HelpHint.jsx';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { AdvancedAnalysisSettings } from './ProviderSettings.jsx';
import { t } from '../../../strings/index.js';

export function ModelTextInput({ label, value, placeholder, onChange, required }) {
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
        aria-label={label ? t('settings.modelNameAria', { label }) : t('settings.modelAria')}
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
      />
    </div>
  );
}

function AnalysisModelsRow({ state, update, analysisHint }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label-row">
          <span className="settings-label">{t('settings.analysisModels')}</span>
          {analysisHint && <HelpHint label={t('settings.analysisModelsHelpAria')}>{analysisHint}</HelpHint>}
        </span>
        <span className="settings-description">{t('settings.analysisModelsDesc')}</span>
      </div>
      <div className="settings-model-overrides">
        <ModelTextInput label={t('settings.fast')} value={state['model-fast']} onChange={(v) => update('model-fast', v)} />
        <ModelTextInput label={t('settings.balanced')} value={state['model-balanced']} onChange={(v) => update('model-balanced', v)} />
        <ModelTextInput label={t('settings.thorough')} value={state['model-thorough']} onChange={(v) => update('model-thorough', v)} />
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
        <AnalysisModelsRow state={state} update={update} analysisHint={analysisHint} />
        <AnalysisPowerRow power={power} setPower={setPower} persistPower={persistPower} />
        <CmdOverrideRow providerId={providerId} state={state} update={update} cmdPathError={cmdPathError} validateCmdPath={validateCmdPath} />
        <AdvancedAnalysisSettings state={state} update={update} />
      </div>
    </details>
  );
}
