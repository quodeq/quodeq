import { DEFAULT_MODELS, MODEL_STORAGE_PREFIX } from '../../evaluation/components/powerLevels.js';

const AI_MODEL_STORAGE_KEY = 'cc-ai-model';
const AI_CMD_STORAGE_KEY = 'cc-ai-cmd';

export { AI_MODEL_STORAGE_KEY, AI_CMD_STORAGE_KEY };

function ClientSelector({ aiCmd, availableClients }) {
  const { value, onApply } = aiCmd;
  return (
    <>
      <div className={`settings-row${!value ? ' settings-row--last' : ''}`}>
        <div className="settings-row-label">
          <span className="settings-label">Client</span>
          <span className="settings-description">CLI tool used to run the analysis</span>
        </div>
        {availableClients === null ? (
          <span className="settings-description">Detecting…</span>
        ) : availableClients.filter((c) => c.id === 'claude').length > 0 ? (
          <div className="theme-toggle">
            {availableClients.filter((c) => c.id === 'claude').map(({ id, label }) => (
              <button
                key={id}
                type="button"
                className={`theme-toggle-btn${value === id ? ' active' : ''}`}
                onClick={() => onApply(id)}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
      {availableClients !== null && !availableClients.some((c) => c.id === 'claude') && (
        <div className="settings-row settings-row--last settings-install-guide">
          <div className="settings-row-label">
            <span className="settings-label">Claude not detected</span>
            <span className="settings-description">
              Install Claude Code and restart Quodeq.
            </span>
          </div>
          <div className="settings-install-options">
            <div className="settings-install-item">
              <span className="settings-install-name">Claude</span>
              <code className="settings-install-cmd">npm i -g @anthropic-ai/claude-code</code>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function handleModelChange(level, value, setter) {
  setter(value);
  if (value) {
    localStorage.setItem(`${MODEL_STORAGE_PREFIX}${level}`, value);
  } else {
    localStorage.removeItem(`${MODEL_STORAGE_PREFIX}${level}`);
  }
}

function ModelOverrideInput({ label, value, setter, level, placeholder }) {
  return (
    <div className="settings-model-field">
      <label className="settings-model-label">{label}</label>
      <input
        type="text"
        className="settings-model-input"
        value={value}
        placeholder={placeholder}
        onChange={(e) => handleModelChange(level, e.target.value, setter)}
      />
    </div>
  );
}

function ModelSettings({ aiCmd, models }) {
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
          onChange={(e) => {
            const v = e.target.value;
            onAiModelChange(v);
            if (v) {
              localStorage.setItem(AI_MODEL_STORAGE_KEY, v);
            } else {
              localStorage.removeItem(AI_MODEL_STORAGE_KEY);
            }
          }}
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
          <ModelOverrideInput label="Fast" value={fast} setter={onFastChange} level={1} placeholder={DEFAULT_MODELS[1]} />
          <ModelOverrideInput label="Balanced" value={balanced} setter={onBalancedChange} level={2} placeholder={DEFAULT_MODELS[2]} />
          <ModelOverrideInput label="Thorough" value={thorough} setter={onThoroughChange} level={3} placeholder={DEFAULT_MODELS[3]} />
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
