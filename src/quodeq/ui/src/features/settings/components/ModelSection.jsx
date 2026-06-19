import { useMemo } from 'react';
import { DEFAULT_MODELS, MODEL_STORAGE_PREFIX } from '../../evaluation/components/powerLevels.js';
import { AI_CMD_STORAGE_KEY } from '../../../constants.js';

const AI_MODEL_STORAGE_KEY = 'cc-ai-model';

const MODEL_LEVEL_FAST = 1;
const MODEL_LEVEL_BALANCED = 2;
const MODEL_LEVEL_THOROUGH = 3;

export { AI_MODEL_STORAGE_KEY, AI_CMD_STORAGE_KEY };

function ClientSelector({ aiCmd = {}, availableClients }) {
  const { value, onApply } = aiCmd;
  if (availableClients == null) {
    return (
      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Client</span>
          <span className="settings-description">Detecting...</span>
        </div>
      </div>
    );
  }

  const cliClients = useMemo(() => availableClients.filter((c) => c.type === 'cli' || !c.type), [availableClients]);
  const apiClients = useMemo(() => availableClients.filter((c) => c.type === 'api'), [availableClients]);

  return (
    <>
      <div className={`settings-row${!value && apiClients.length === 0 ? ' settings-row--last' : ''}`}>
        <div className="settings-row-label">
          <span className="settings-label">Client</span>
          <span className="settings-description">CLI tool or API provider for analysis</span>
        </div>
        <div className="settings-pill-group">
          {cliClients.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={`settings-pill${value === id ? ' settings-pill--active' : ''}`}
              onClick={() => onApply(id)}
            >
              {label}
            </button>
          ))}
          {apiClients.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              className={`settings-pill${value === id ? ' settings-pill--active' : ''}`}
              onClick={() => onApply(id)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {cliClients.length === 0 && apiClients.length === 0 && (
        <div className="settings-row settings-row--last settings-install-guide">
          <div className="settings-row-label">
            <span className="settings-label">No providers detected</span>
            <span className="settings-description">
              Install a CLI tool or configure an API provider.
            </span>
          </div>
        </div>
      )}
    </>
  );
}

function handleModelChange(level, value, setter, storageKey = `${MODEL_STORAGE_PREFIX}${level}`, storage = localStorage) {
  setter(value);
  if (value) {
    storage.setItem(storageKey, value);
  } else {
    storage.removeItem(storageKey);
  }
}

function ModelOverrideInput({ label, value, setter, level, placeholder }) {
  const inputId = `model-override-${level}`;
  return (
    <div className="settings-model-field">
      <label className="settings-model-label" htmlFor={inputId}>{label}</label>
      <input
        type="text"
        id={inputId}
        className="settings-model-input"
        value={value}
        placeholder={placeholder}
        onChange={(e) => handleModelChange(level, e.target.value, setter)}
        autoCapitalize="off"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
      />
    </div>
  );
}

function ModelSettings({ aiCmd = {}, models }) {
  const { value: aiCmdValue } = aiCmd;
  const { aiModel, onAiModelChange, fast, onFastChange, balanced, onBalancedChange, thorough, onThoroughChange } = models;
  if (!aiCmdValue) return null;
  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model</span>
          <span className="settings-description">
            Override the default model for all operations. Leave blank to use your client's default.
          </span>
        </div>
        <input
          type="text"
          className="settings-model-input"
          value={aiModel}
          placeholder="default"
          onChange={(e) => handleModelChange(null, e.target.value, onAiModelChange, AI_MODEL_STORAGE_KEY)}
          aria-label="Model override"
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
        />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis models</span>
          <span className="settings-description">
            Override the AI model used by subagents during code evaluation. Leave blank to use the defaults.
          </span>
        </div>
        <div className="settings-model-overrides">
          <ModelOverrideInput label="Fast" value={fast} setter={onFastChange} level={MODEL_LEVEL_FAST} placeholder={DEFAULT_MODELS[MODEL_LEVEL_FAST]} />
          <ModelOverrideInput label="Balanced" value={balanced} setter={onBalancedChange} level={MODEL_LEVEL_BALANCED} placeholder={DEFAULT_MODELS[MODEL_LEVEL_BALANCED]} />
          <ModelOverrideInput label="Thorough" value={thorough} setter={onThoroughChange} level={MODEL_LEVEL_THOROUGH} placeholder={DEFAULT_MODELS[MODEL_LEVEL_THOROUGH]} />
        </div>
      </div>
    </>
  );
}

export default function ModelSection({ aiCmd, models, availableClients }) {
  return (
    <>
      <ClientSelector aiCmd={aiCmd} availableClients={availableClients} />
      <ModelSettings aiCmd={aiCmd} models={models} />
    </>
  );
}
