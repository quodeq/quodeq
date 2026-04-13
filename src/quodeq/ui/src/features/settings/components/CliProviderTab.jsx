import { useState, useEffect, useMemo } from 'react';
import { getKnownModels } from '../../../api/index.js';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { STORAGE_KEY as POWER_KEY } from '../../evaluation/components/powerLevels.js';
import ProviderSettings from './ProviderSettings.jsx';

function ModelSuggestInput({ label, value, suggestions, placeholder, onChange, required }) {
  return (
    <div className="settings-model-field">
      {label && <label className="settings-model-label">{label}</label>}
      <input
        type="text"
        className={`settings-model-input${required && !value ? ' settings-model-input--required' : ''}`}
        list={`models-${label}`}
        value={value}
        placeholder={placeholder || 'Select or type model'}
        onChange={(e) => onChange(e.target.value)}
      />
      <datalist id={`models-${label}`}>
        {suggestions.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
      </datalist>
    </div>
  );
}

export default function CliProviderTab({ providerId, state, update }) {
  const [suggestions, setSuggestions] = useState([]);
  const [power, setPower] = useState(() => {
    try { return Number(localStorage.getItem(POWER_KEY)) || 2; } catch { return 2; }
  });

  function persistPower(level) {
    setPower(level);
    try { localStorage.setItem(POWER_KEY, String(level)); } catch { /* */ }
  }

  useEffect(() => {
    getKnownModels()
      .then((data) => setSuggestions(data[providerId] || []))
      .catch(() => setSuggestions([]));
  }, [providerId]);

  const { fast, balanced, thorough } = useMemo(() => {
    const f = [], b = [], t = [];
    for (const m of suggestions) {
      if (m.tier === 'fast') f.push(m);
      else if (m.tier === 'balanced') b.push(m);
      else if (m.tier === 'thorough') t.push(m);
    }
    return { fast: f, balanced: b, thorough: t };
  }, [suggestions]);

  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">Select the model to use for evaluation</span>
        </div>
        <div className="settings-model-field">
          <ModelSuggestInput value={state.model} suggestions={suggestions} onChange={(v) => update('model', v)} required />
          {!state.model && <span className="settings-model-hint">Select a model to get started</span>}
        </div>
      </div>
      <details className="settings-advanced">
        <summary className="settings-advanced-toggle">Advanced</summary>
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Analysis power</span>
            <span className="settings-description">Controls which model tier is used for analysis</span>
          </div>
          <PowerSelector value={power} onChange={setPower} onPersist={persistPower} />
        </div>
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Analysis models</span>
            <span className="settings-description">Override models per power level</span>
          </div>
          <div className="settings-model-overrides">
            <ModelSuggestInput label="Fast" value={state['model-fast']} suggestions={fast.length ? fast : suggestions} placeholder={fast[0]?.label} onChange={(v) => update('model-fast', v)} />
            <ModelSuggestInput label="Balanced" value={state['model-balanced']} suggestions={balanced.length ? balanced : suggestions} placeholder={balanced[0]?.label} onChange={(v) => update('model-balanced', v)} />
            <ModelSuggestInput label="Thorough" value={state['model-thorough']} suggestions={thorough.length ? thorough : suggestions} placeholder={thorough[0]?.label} onChange={(v) => update('model-thorough', v)} />
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Max parallel agents</span>
            <span className="settings-description">Number of subagents to run in parallel (1–10)</span>
          </div>
          <input
            type="number"
            className="settings-model-input"
            min={1}
            max={10}
            value={parseInt(state.subagents || '5', 10)}
            onBlur={(e) => update('subagents', Math.max(1, Math.min(10, parseInt(e.target.value, 10) || 5)))}
            onChange={(e) => update('subagents', e.target.value)}
          />
        </div>
        <ProviderSettings state={state} update={update} providerType="cli" />
      </details>
    </>
  );
}
