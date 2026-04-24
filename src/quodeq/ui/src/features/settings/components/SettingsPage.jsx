import { useState, useEffect } from 'react';
import { getHealth, getProviderConfigs } from '../../../api/index.js';
import AboutSection from './AboutSection.jsx';
import AppearanceSection from './AppearanceSection.jsx';
import ProviderTabs from './ProviderTabs.jsx';
import ServerSection from './ServerSection.jsx';
import { SETTINGS_TOAST_SEEN_KEY } from '../../../constants.js';
import { TermHeader } from '../../../components/terminal/index.js';

const _SETTINGS_PHRASES = [
  'quode with cuore \u2665',
  'human aligned quode',
  'quode safe',
  'navigate your quode to excellence',
  'code quality compass',
];

const TOAST_DISMISS_MS = 8000;

function SettingsToast({ onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, TOAST_DISMISS_MS);
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
    try { return !localStorage.getItem(SETTINGS_TOAST_SEEN_KEY); } catch { return true; }
  });

  function dismissToast() {
    setShowToast(false);
    try { localStorage.setItem(SETTINGS_TOAST_SEEN_KEY, '1'); } catch {}
  }

  useEffect(() => {
    setSettingsPhrase(_SETTINGS_PHRASES[Math.floor(Math.random() * _SETTINGS_PHRASES.length)]);
    getHealth().then((d) => setAppVersion(d.version || null)).catch((err) => console.warn('Failed to fetch app version:', err));
    getProviderConfigs().then(setProviderConfigs).catch(() => setProviderConfigs({}));
  }, []);

  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader
        name="settings"
        sub="manage your quodeq preferences"
      />
      {showToast && <SettingsToast onDismiss={dismissToast} />}
      <div className="settings-grid">
        <ProviderTabs providerConfigs={providerConfigs} />

        <div className="settings-grid-col">
          <ServerSection />
          <AppearanceSection themeMode={themeMode} themeFamily={themeFamily} onApplyMode={onApplyMode} onApplyFamily={onApplyFamily} />
          <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
        </div>
      </div>
    </div>
  );
}
