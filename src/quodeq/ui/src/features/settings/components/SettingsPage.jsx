import { useState, useEffect } from 'react';
import { getHealth, getProviderConfigs } from '../../../api/index.js';
import AboutSection from './AboutSection.jsx';
import AppearanceSection from './AppearanceSection.jsx';
import ProviderTabs from './ProviderTabs.jsx';
import ServerSection from './ServerSection.jsx';
import { TermHeader } from '../../../components/terminal/index.js';

const _SETTINGS_PHRASES = [
  'quode with cuore ♥',
  'human aligned quode',
  'quode safe',
  'navigate your quode to excellence',
  'code quality compass',
];

export default function SettingsPage({ theme }) {
  const { mode: themeMode, family: themeFamily, onApplyMode, onApplyFamily } = theme;
  const [appVersion, setAppVersion] = useState(null);
  const [settingsPhrase, setSettingsPhrase] = useState('');
  const [providerConfigs, setProviderConfigs] = useState({});

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
