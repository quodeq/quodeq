import { useState, useEffect } from 'react';
import { getHealth, getProviderConfigs } from '../../../api/index.js';
import SettingsAside from './SettingsAside.jsx';
import AboutSection from './AboutSection.jsx';
import ProviderTabs from './ProviderTabs.jsx';
import ServerSection from './ServerSection.jsx';

const MODE_OPTIONS = [
  { value: 'system',   label: 'System' },
  { value: 'light',    label: 'Light' },
  { value: 'dark',     label: 'Dark' },
];

const FAMILY_OPTIONS = [
  { value: 'daruma',    label: 'Daruma' },
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

const SETTINGS_TOAST_KEY = 'quodeq-settings-toast-seen';

function SettingsToast({ onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 8000);
    return () => clearTimeout(timer);
  }, [onDismiss]);

  return (
    <div className="job-error-toast settings-info-toast" onClick={onDismiss}>
      Cloud providers (Claude, Codex, Gemini) use their API tokens. Ollama runs locally at no cost.
    </div>
  );
}

export default function SettingsPage({ theme }) {
  const { mode: themeMode, family: themeFamily, onApplyMode, onApplyFamily } = theme;
  const [appVersion, setAppVersion] = useState(null);
  const [settingsPhrase, setSettingsPhrase] = useState('');
  const [providerConfigs, setProviderConfigs] = useState({});
  const [showToast, setShowToast] = useState(() => {
    try { return !localStorage.getItem(SETTINGS_TOAST_KEY); } catch { return true; }
  });

  function dismissToast() {
    setShowToast(false);
    try { localStorage.setItem(SETTINGS_TOAST_KEY, '1'); } catch {}
  }

  useEffect(() => {
    setSettingsPhrase(_SETTINGS_PHRASES[Math.floor(Math.random() * _SETTINGS_PHRASES.length)]);
    getHealth().then((d) => setAppVersion(d.version || null)).catch((err) => console.warn('Failed to fetch app version:', err));
    getProviderConfigs().then(setProviderConfigs).catch(() => setProviderConfigs({}));
  }, []);

  return (
    <div className="settings-page">
      <SettingsHeader />
      {showToast && <SettingsToast onDismiss={dismissToast} />}
      <div className="settings-body settings-body--full">
        <div className="settings-grid">
          <ProviderTabs providerConfigs={providerConfigs} />

          <div className="settings-grid-col">
            <ServerSection />
            <ThemeSection themeMode={themeMode} themeFamily={themeFamily} onApplyMode={onApplyMode} onApplyFamily={onApplyFamily} />
            <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
          </div>
        </div>
      </div>
    </div>
  );
}
