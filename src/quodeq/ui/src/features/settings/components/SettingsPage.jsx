import { useState, useEffect } from 'react';
import { getHealth, getProviderConfigs } from '../../../api/index.js';
import AboutSection from './AboutSection.jsx';
import AppearanceSection from './AppearanceSection.jsx';
import UpdatesSection from './UpdatesSection.jsx';
import ProviderTabs from './ProviderTabs.jsx';
import AssistantProviderTabs from './AssistantProviderTabs.jsx';
import TerminalSection from './TerminalSection.jsx';
import ServerSection from './ServerSection.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

const _SETTINGS_PHRASES = [
  'quode with cuore ♥',
  'human aligned quode',
  'quode safe',
  'navigate your quode to excellence',
  'code quality compass',
];

export default function SettingsPage({ theme, onOpenGradeFormula }) {
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
        <AssistantProviderTabs providerConfigs={providerConfigs} />
        <TerminalSection />
        <ServerSection />
        <section className="panel settings-section">
          <div className="panel-header">
            <SectionLabel marker="▶">Grade formula</SectionLabel>
          </div>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">Grade formula</span>
              <span className="settings-description">
                Tune how violations and compliance turn into grades. Changes rescore all runs.
              </span>
            </div>
            <button type="button" className="settings-pill" onClick={onOpenGradeFormula}>
              open editor
            </button>
          </div>
        </section>
        <AppearanceSection themeMode={themeMode} themeFamily={themeFamily} onApplyMode={onApplyMode} onApplyFamily={onApplyFamily} />
        <UpdatesSection />
        <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
      </div>
    </div>
  );
}
