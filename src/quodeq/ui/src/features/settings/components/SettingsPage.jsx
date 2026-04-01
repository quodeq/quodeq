import { useState, useEffect } from 'react';
import { getHealth, getAiClients } from '../../../api/index.js';
import PowerSelector from '../../evaluation/components/PowerSelector.jsx';
import SettingsAside from './SettingsAside.jsx';
import AboutSection from './AboutSection.jsx';
import ModelSection from './ModelSection.jsx';
import { DEFAULT_MAX_SUBAGENTS, DEFAULT_POOL_BUDGET, SUBAGENTS_STORAGE_KEY, POOL_BUDGET_STORAGE_KEY, AI_CMD_STORAGE_KEY } from '../../../constants.js';

const MIN_SUBAGENTS = 1;
const MAX_SUBAGENTS = 10;
const MIN_POOL_BUDGET_MINS = 1;
const MAX_POOL_BUDGET_MINS = 60;
const DEFAULT_POOL_BUDGET_MINS = 10;

function persistSetting(key, value) {
  localStorage.setItem(key, String(value));
}

const MODE_OPTIONS = [
  { value: 'system',   label: 'System' },
  { value: 'light',    label: 'Light' },
  { value: 'dark',     label: 'Dark' },
];

const FAMILY_OPTIONS = [
  { value: 'daruma',    label: 'Daruma' },
  { value: 'flynn',     label: 'Flynn' },
  { value: 'neo',       label: 'Neo' },
  { value: 'ifrit',     label: 'Ifrit' },
  { value: 'deckard',   label: 'Deckard' },
  { value: 'galadriel', label: 'Galadriel' },
];

const _SETTINGS_PHRASES = [
  'quode with cuore \u2665',
  'human aligned quode',
  'quode safe',
  'navigate your quode to excellence',
  'code quality compass',
];

function ThemeSection({ themeMode, themeFamily, onApplyMode, onApplyFamily }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <h2 className="settings-section-title">Appearance</h2>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Mode</span>
          <span className="settings-description">Choose light, dark, or follow your system</span>
        </div>
        <div className="theme-toggle">
          {MODE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`theme-toggle-btn${themeMode === value ? ' active' : ''}`}
              onClick={() => onApplyMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Theme</span>
          <span className="settings-description">Pick a color palette</span>
        </div>
        <div className="theme-family-picker">
          {FAMILY_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`theme-family-card${themeFamily === value ? ' active' : ''}`}
              onClick={() => onApplyFamily(value)}
            >
              <span className="theme-family-label">{label}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function clampSubagents(value) {
  return Math.max(MIN_SUBAGENTS, Math.min(MAX_SUBAGENTS, parseInt(value, 10) || DEFAULT_MAX_SUBAGENTS));
}

function persistSubagents(value, setter) {
  const v = clampSubagents(value);
  setter(v);
  persistSetting(SUBAGENTS_STORAGE_KEY, v);
}

function clampPoolBudget(value) {
  return Math.max(MIN_POOL_BUDGET_MINS, Math.min(MAX_POOL_BUDGET_MINS, parseInt(value, 10) || DEFAULT_POOL_BUDGET_MINS));
}

function persistPoolBudget(value, setter) {
  const v = clampPoolBudget(value);
  setter(v);
  persistSetting(POOL_BUDGET_STORAGE_KEY, v * 60);
}

function SubagentsRow({ subagents }) {
  const { max, setMax } = subagents;
  return (
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
        value={max}
        onChange={(e) => persistSubagents(e.target.value, setMax)}
      />
    </div>
  );
}

function PoolBudgetRow({ subagents }) {
  const { poolBudgetMinutes, setPoolBudgetMinutes } = subagents;
  return (
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
        onChange={(e) => persistPoolBudget(e.target.value, setPoolBudgetMinutes)}
      />
    </div>
  );
}

function AnalysisSection({ analysis, subagents }) {
  const { power, onChange, onPersist } = analysis;
  return (
    <>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Analysis power</span>
          <span className="settings-description">
            Controls the AI model used for analysis. Higher power gives more thorough results but takes longer.
          </span>
        </div>
        <PowerSelector value={power} onChange={onChange} onPersist={onPersist} />
      </div>
      <SubagentsRow subagents={subagents} />
      <PoolBudgetRow subagents={subagents} />
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

function SettingsHeader() {
  return (
    <div className="settings-header">
      <div className="settings-header-content">
        <div className="settings-header-left">
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
        <div className="settings-header-center">
          <SettingsAside />
        </div>
      </div>
    </div>
  );
}

function useSettingsState(aiCmd, onApplyAiCmd) {
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

  return { maxSubagents, setMaxSubagents, poolBudgetMinutes, setPoolBudgetMinutes, availableClients, appVersion, settingsPhrase };
}

export default function SettingsPage({ theme, models, analysis, verification }) {
  const { mode: themeMode, family: themeFamily, onApplyMode, onApplyFamily } = theme;
  const { aiCmd, onApplyAiCmd } = models;
  const { power: analysisPower, onPowerChange: onAnalysisPowerChange, onPersist: onPersistPower } = analysis;
  const { enabled: verifyFindings, onApply: onApplyVerifyFindings } = verification;
  const { maxSubagents, setMaxSubagents, poolBudgetMinutes, setPoolBudgetMinutes, availableClients, appVersion, settingsPhrase } = useSettingsState(aiCmd, onApplyAiCmd);

  return (
    <div className="settings-page">
      <SettingsHeader />
      <div className="settings-body settings-body--full">
        <div className="settings-grid">
          <section className="panel settings-section">
            <div className="panel-header">
              <h2 className="settings-section-title">Analysis</h2>
              <p className="settings-section-description">Configure the AI client used when running evaluations</p>
            </div>
            <ModelSection
              aiCmd={{ value: aiCmd, onApply: onApplyAiCmd }}
              models={{
                aiModel: models.aiModel, onAiModelChange: models.onAiModelChange,
                fast: models.fast, onFastChange: models.onFastChange,
                balanced: models.balanced, onBalancedChange: models.onBalancedChange,
                thorough: models.thorough, onThoroughChange: models.onThoroughChange,
              }}
              availableClients={availableClients}
            />
            <AnalysisSection
              analysis={{ power: analysisPower, onChange: onAnalysisPowerChange, onPersist: onPersistPower }}
              subagents={{ max: maxSubagents, setMax: setMaxSubagents, poolBudgetMinutes, setPoolBudgetMinutes }}
            />
            <VerificationSection verifyFindings={verifyFindings} onApplyVerifyFindings={onApplyVerifyFindings} />
          </section>

          <div className="settings-grid-col">
            <ThemeSection themeMode={themeMode} themeFamily={themeFamily} onApplyMode={onApplyMode} onApplyFamily={onApplyFamily} />
            <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
          </div>
        </div>
      </div>
    </div>
  );
}
