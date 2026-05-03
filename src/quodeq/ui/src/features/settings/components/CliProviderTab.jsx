import { useState } from 'react';
import { MIN_SUBAGENTS, MAX_SUBAGENTS, DEFAULT_SUBAGENTS } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { STORAGE_KEY as POWER_KEY } from '../../evaluation/components/powerLevels.js';
import { TimeLimitSetting, AdvancedAnalysisSettings, SUBAGENTS_HINT_REMOTE } from './ProviderSettings.jsx';

const DEFAULT_POWER_LEVEL = 2;

const MODEL_HINTS = {
  claude: (
    <>
      Type <code>haiku</code>, <code>sonnet</code>, or <code>opus</code>. Claude Code will pick the latest version for you. If you want a specific version, just paste its full id. You can find them in Anthropic&apos;s docs.
    </>
  ),
  codex: (
    <>
      Type the model id you want to use, like <code>gpt-5-mini</code> or <code>gpt-5</code>. The full list lives in OpenAI&apos;s docs.
    </>
  ),
  gemini: (
    <>
      Type the model id you want, like <code>gemini-2.5-flash-lite</code>, <code>gemini-2.5-flash</code>, or <code>gemini-2.5-pro</code>. The full list is in Google&apos;s docs.
    </>
  ),
};

const ANALYSIS_MODEL_HINTS = {
  claude: (
    <>
      Want a different model for different tasks? Pick one per tier (Fast, Balanced, Thorough). Type <code>haiku</code>, <code>sonnet</code>, or <code>opus</code>, and Claude Code picks the latest version. Anything you leave blank just uses the model you chose above.
    </>
  ),
  codex: (
    <>
      Want a different model for different tasks? Pick one per tier (Fast, Balanced, Thorough). For example, <code>gpt-5-mini</code> for Fast and <code>gpt-5</code> for Thorough. Anything you leave blank just uses the model you chose above.
    </>
  ),
  gemini: (
    <>
      Want a different model for different tasks? Pick one per tier (Fast, Balanced, Thorough). For example, <code>gemini-2.5-flash-lite</code> for Fast and <code>gemini-2.5-pro</code> for Thorough. Anything you leave blank just uses the model you chose above.
    </>
  ),
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
        placeholder={placeholder || 'Type model id'}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label ? `${label} model` : 'Model'}
      />
    </div>
  );
}

export default function CliProviderTab({ providerId, state, update }) {
  const [power, setPower] = useState(() => {
    try { return Number(localStorage.getItem(POWER_KEY)) || DEFAULT_POWER_LEVEL; } catch { return DEFAULT_POWER_LEVEL; }
  });

  function persistPower(level) {
    setPower(level);
    try { localStorage.setItem(POWER_KEY, String(level)); } catch { /* */ }
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
            <span className="settings-label">Model</span>
            {hint && <HelpHint label="Model help">{hint}</HelpHint>}
          </span>
          <span className="settings-description">Pick the model you want to use.</span>
        </div>
        <div className="settings-model-field">
          <ModelTextInput value={state.model} onChange={(v) => update('model', v)} required />
          {!state.model && <span className="settings-model-hint">Pick a model to get started.</span>}
        </div>
      </div>
      <TimeLimitSetting state={state} update={update} providerType="cli" />
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">Max parallel agents</span>
            <HelpHint label="Max parallel agents help">{SUBAGENTS_HINT_REMOTE}</HelpHint>
          </span>
          <span className="settings-description">How many subagents work side by side. Pick a number from 1 to 10.</span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_SUBAGENTS}
          max={MAX_SUBAGENTS}
          value={state.subagents ?? ''}
          onChange={(e) => update('subagents', e.target.value)}
          onBlur={(e) => { if (e.target.value !== '') update('subagents', clampSubagents(e.target.value)); }}
          aria-label="Max parallel agents"
        />
      </div>
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">Advanced</summary>
        <div className="settings-advanced-content">
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label-row">
                <span className="settings-label">Analysis models</span>
                {analysisHint && <HelpHint label="Analysis models help">{analysisHint}</HelpHint>}
              </span>
              <span className="settings-description">Optional. Anything you leave blank uses the model you chose above.</span>
            </div>
            <div className="settings-model-overrides">
              <ModelTextInput label="Fast" value={state['model-fast']} onChange={(v) => update('model-fast', v)} />
              <ModelTextInput label="Balanced" value={state['model-balanced']} onChange={(v) => update('model-balanced', v)} />
              <ModelTextInput label="Thorough" value={state['model-thorough']} onChange={(v) => update('model-thorough', v)} />
            </div>
          </div>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">Analysis power</span>
              <span className="settings-description">Pick which tier above the evaluation should use.</span>
            </div>
            <PowerSelector value={power} onChange={setPower} onPersist={persistPower} />
          </div>
          <AdvancedAnalysisSettings state={state} update={update} />
        </div>
      </details>
    </>
  );
}
