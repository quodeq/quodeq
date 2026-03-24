import { useState, useEffect } from 'react';
import { getHealth, getAiClients } from '../../../api/index.js';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import { DEFAULT_MODELS, MODEL_STORAGE_PREFIX } from '../../evaluation/components/powerLevels.js';
import SettingsAside from './SettingsAside.jsx';
import AboutSection from './AboutSection.jsx';
import { DEFAULT_MAX_SUBAGENTS, DEFAULT_POOL_BUDGET, SUBAGENTS_STORAGE_KEY, POOL_BUDGET_STORAGE_KEY } from '../../../constants.js';

const AI_MODEL_STORAGE_KEY = 'cc-ai-model';
const AI_CMD_STORAGE_KEY = 'cc-ai-cmd';
const MIN_SUBAGENTS = 1;
const MAX_SUBAGENTS = 10;
const MIN_POOL_BUDGET_MINS = 1;
const MAX_POOL_BUDGET_MINS = 60;
const DEFAULT_POOL_BUDGET_MINS = 10;

const THEME_OPTIONS = [
  { value: 'system',   label: 'System' },
  { value: 'light',    label: 'Light' },
  { value: 'dark',     label: 'Dark' },
  { value: 'ember',    label: 'Ember' },
  { value: 'forest',   label: 'Forest' },
  { value: 'midnight', label: 'Midnight' },
  { value: 'slate',    label: 'Slate' },
  { value: 'horizon',  label: 'Horizon' },
];

const _SETTINGS_PHRASES = [
  'quode with cuore \u2665',
  'human aligned quode',
  'quode safe',
  'navigate your quode to excellence',
  'code quality compass',
];

function ThemeSection({ themePreference, onApplyTheme }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <h2 className="settings-section-title">Appearance</h2>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Theme</span>
          <span className="settings-description">Choose how Quodeq looks to you</span>
        </div>
        <div className="theme-toggle">
          {THEME_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`theme-toggle-btn${themePreference === value ? ' active' : ''}`}
              onClick={() => onApplyTheme(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function ModelSection({ aiCmd, onApplyAiCmd, aiModel, onAiModelChange, modelFast, onModelFastChange, modelBalanced, onModelBalancedChange, modelThorough, onModelThoroughChange, availableClients }) {
  return (
    <>
      <div className={`settings-row${!aiCmd ? ' settings-row--last' : ''}`}>
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
                className={`theme-toggle-btn${aiCmd === id ? ' active' : ''}`}
                onClick={() => onApplyAiCmd(id)}
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
      {aiCmd && (
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
      )}
      {aiCmd && (
        <div className="settings-row">
          <div className="settings-row-label">
            <span className="settings-label">Analysis models</span>
            <span className="settings-description">
              Override the AI model used by subagents during code evaluation. Leave blank to use the defaults.
            </span>
          </div>
          <div className="settings-model-overrides">
          {[
            { label: 'Fast', value: modelFast, setter: onModelFastChange, level: 1, placeholder: DEFAULT_MODELS[1] },
            { label: 'Balanced', value: modelBalanced, setter: onModelBalancedChange, level: 2, placeholder: DEFAULT_MODELS[2] },
            { label: 'Thorough', value: modelThorough, setter: onModelThoroughChange, level: 3, placeholder: DEFAULT_MODELS[3] },
          ].map(({ label, value, setter, level, placeholder }) => (
            <div key={level} className="settings-model-field">
              <label className="settings-model-label">{label}</label>
              <input
                type="text"
                className="settings-model-input"
                value={value}
                placeholder={placeholder}
                onChange={(e) => {
                  const v = e.target.value;
                  setter(v);
                  if (v) {
                    localStorage.setItem(`${MODEL_STORAGE_PREFIX}${level}`, v);
                  } else {
                    localStorage.removeItem(`${MODEL_STORAGE_PREFIX}${level}`);
                  }
                }}
              />
            </div>
          ))}
          </div>
        </div>
      )}
    </>
  );
}

function AnalysisSection({ analysisPower, onAnalysisPowerChange, maxSubagents, setMaxSubagents, poolBudgetMinutes, setPoolBudgetMinutes }) {
  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis power</span>
          <span className="settings-description">
            Controls the AI model used for analysis. Higher power gives more thorough results but takes longer.
          </span>
        </div>
        <PowerSelector value={analysisPower} onChange={onAnalysisPowerChange} />
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Max parallel agents</span>
          <span className="settings-description">
            Maximum number of subagents to run in parallel during evaluation (1–10). Higher values speed up analysis but use more resources.
          </span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_SUBAGENTS}
          max={MAX_SUBAGENTS}
          value={maxSubagents}
          onChange={(e) => {
            const v = Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, parseInt(e.target.value, 10) || DEFAULT_MAX_SUBAGENTS));
            setMaxSubagents(v);
            localStorage.setItem(SUBAGENTS_STORAGE_KEY, String(v));
          }}
        />
      </div>
      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">Analysis time limit</span>
          <span className="settings-description">
            Maximum time allowed for the analysis pool to run (1–60 minutes). Evaluations exceeding this limit will stop early.
          </span>
        </div>
        <input
          type="number"
          className="settings-model-input"
          min={MIN_POOL_BUDGET_MINS}
          max={MAX_POOL_BUDGET_MINS}
          value={poolBudgetMinutes}
          onChange={(e) => {
            const v = Math.max(MIN_POOL_BUDGET_MINS, Math.min(MAX_POOL_BUDGET_MINS, parseInt(e.target.value, 10) || DEFAULT_POOL_BUDGET_MINS));
            setPoolBudgetMinutes(v);
            localStorage.setItem(POOL_BUDGET_STORAGE_KEY, String(v * 60));
          }}
        />
      </div>
    </>
  );
}

function VerificationSection({ verifyFindings, onApplyVerifyFindings }) {
  return (
    <div className="settings-row">
      <div className="settings-row-label">
        <span className="settings-label">Verify findings</span>
        <span className="settings-description">
          After analysis, verify findings from the previous evaluation against the current code. Confirms which violations persist, detects fixes, and hunts for missing compliance evidence. Improves grade consistency across runs.
        </span>
      </div>
      <div className="theme-toggle">
        <button
          type="button"
          className={`theme-toggle-btn${verifyFindings ? ' active' : ''}`}
          onClick={() => onApplyVerifyFindings(true)}
        >On</button>
        <button
          type="button"
          className={`theme-toggle-btn${!verifyFindings ? ' active' : ''}`}
          onClick={() => onApplyVerifyFindings(false)}
        >Off</button>
      </div>
    </div>
  );
}

export default function SettingsPage({ theme, models, analysis, verification }) {
  const { preference: themePreference, onApply: onApplyTheme } = theme;
  const {
    aiCmd, onApplyAiCmd, aiModel, onAiModelChange,
    fast: modelFast, onFastChange: onModelFastChange,
    balanced: modelBalanced, onBalancedChange: onModelBalancedChange,
    thorough: modelThorough, onThoroughChange: onModelThoroughChange,
  } = models;
  const { power: analysisPower, onPowerChange: onAnalysisPowerChange } = analysis;
  const { enabled: verifyFindings, onApply: onApplyVerifyFindings } = verification;

  const [maxSubagents, setMaxSubagents] = useState(() => parseInt(localStorage.getItem(SUBAGENTS_STORAGE_KEY) || String(DEFAULT_MAX_SUBAGENTS), 10));
  const [poolBudgetMinutes, setPoolBudgetMinutes] = useState(() => Math.round(parseInt(localStorage.getItem(POOL_BUDGET_STORAGE_KEY) || String(DEFAULT_POOL_BUDGET), 10) / 60));
  const [availableClients, setAvailableClients] = useState(null);
  const [appVersion, setAppVersion] = useState(null);
  const [settingsPhrase, setSettingsPhrase] = useState('');

  useEffect(() => {
    setSettingsPhrase(_SETTINGS_PHRASES[Math.floor(Math.random() * _SETTINGS_PHRASES.length)]);
    if (appVersion === null) {
      getHealth().then((d) => setAppVersion(d.version || null)).catch((err) => console.warn('Failed to fetch app version:', err));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (availableClients !== null) return;
    getAiClients()
      .then((data) => {
        const clients = data.clients || [];
        setAvailableClients(clients);
        if (aiCmd && !clients.some((c) => c.id === aiCmd)) {
          onApplyAiCmd('');
          localStorage.removeItem(AI_CMD_STORAGE_KEY);
        }
        if (!aiCmd && clients.length > 0) {
          onApplyAiCmd(clients[0].id);
        }
      })
      .catch(() => setAvailableClients([]));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="settings-page">
      <div className="settings-header">
        <div className="settings-header-content">
          <div className="settings-page-icon">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M12 2v2.5M12 19.5V22M4.93 4.93l1.77 1.77M17.3 17.3l1.77 1.77M2 12h2.5M19.5 12H22M4.93 19.07l1.77-1.77M17.3 6.7l1.77-1.77" />
            </svg>
          </div>
          <div>
            <h1 className="settings-title">Settings</h1>
            <p className="settings-subtitle">Manage your Quodeq preferences</p>
          </div>
        </div>
      </div>

      <div className="settings-layout">
      <div className="settings-body">
        <ThemeSection themePreference={themePreference} onApplyTheme={onApplyTheme} />

        <section className="panel settings-section">
          <div className="panel-header">
            <h2 className="settings-section-title">Analysis</h2>
            <p className="settings-section-description">Configure the AI client used when running evaluations</p>
          </div>
          <ModelSection
            aiCmd={aiCmd} onApplyAiCmd={onApplyAiCmd}
            aiModel={aiModel} onAiModelChange={onAiModelChange}
            modelFast={modelFast} onModelFastChange={onModelFastChange}
            modelBalanced={modelBalanced} onModelBalancedChange={onModelBalancedChange}
            modelThorough={modelThorough} onModelThoroughChange={onModelThoroughChange}
            availableClients={availableClients}
          />
          <AnalysisSection
            analysisPower={analysisPower} onAnalysisPowerChange={onAnalysisPowerChange}
            maxSubagents={maxSubagents} setMaxSubagents={setMaxSubagents}
            poolBudgetMinutes={poolBudgetMinutes} setPoolBudgetMinutes={setPoolBudgetMinutes}
          />
          <VerificationSection verifyFindings={verifyFindings} onApplyVerifyFindings={onApplyVerifyFindings} />
        </section>
        <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
      </div>

      <SettingsAside />
      </div>
    </div>
  );
}
