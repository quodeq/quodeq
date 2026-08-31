import { useState } from 'react';
import { MIN_SUBAGENTS, MAX_SUBAGENTS, DEFAULT_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { STORAGE_KEY as POWER_KEY } from '../../evaluation/components/powerLevels.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_REMOTE } from './ProviderSettings.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';
import { readString, writeString } from '../../../adapters/storage.js';

const DEFAULT_POWER_LEVEL = 2;

const MODEL_HINTS = {
  claude: tRich('settings.modelHintClaude'),
  codex: tRich('settings.modelHintCodex'),
  gemini: tRich('settings.modelHintGemini'),
};

const ANALYSIS_MODEL_HINTS = {
  claude: tRich('settings.analysisModelsHintClaude'),
  codex: tRich('settings.analysisModelsHintCodex'),
  gemini: tRich('settings.analysisModelsHintGemini'),
};

function ModelTextInput({ label, value, placeholder, onChange, required }) {
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

export default function CliProviderTab({ providerId, state, update }) {
  const [power, setPower] = useState(() => {
    return Number(readString(POWER_KEY)) || DEFAULT_POWER_LEVEL;
  });

  function persistPower(level) {
    setPower(level);
    writeString(POWER_KEY, String(level));
  }

  const hint = MODEL_HINTS[providerId];
  const analysisHint = ANALYSIS_MODEL_HINTS[providerId];

  const clampSubagents = (raw) => {
    const n = parseInt(raw, 10);
    if (Number.isNaN(n)) return String(DEFAULT_SUBAGENTS);
    return String(Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, n)));
  };

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
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
        <div className="settings-advanced-content">
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
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">{t('settings.analysisPower')}</span>
              <span className="settings-description">{t('settings.analysisPowerDesc')}</span>
            </div>
            <PowerSelector value={power} onChange={setPower} onPersist={persistPower} />
          </div>
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
            <input
              type="text"
              className="settings-model-input"
              value={state['cmd-path'] || ''}
              placeholder={providerId}
              onChange={(e) => update('cmd-path', e.target.value.trim())}
              aria-label={t('settings.cmdOverride')}
              autoCapitalize="off"
              autoCorrect="off"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
