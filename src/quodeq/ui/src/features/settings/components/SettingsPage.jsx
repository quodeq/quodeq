import { useState, useEffect } from 'react';
import { getHealth, getProviderConfigs } from '../../../api/index.js';
import AboutSection from './AboutSection.jsx';
import AppearanceSection from './AppearanceSection.jsx';
import UpdatesSection from './UpdatesSection.jsx';
import DesktopSection from './DesktopSection.jsx';
import ProviderTabs from './ProviderTabs.jsx';
import AssistantProviderTabs from './AssistantProviderTabs.jsx';
import EvaluationSection from './EvaluationSection.jsx';
import TerminalSection from './TerminalSection.jsx';
import ServerSection from './ServerSection.jsx';
import SharedRepoSection from './SharedRepoSection.jsx';
import { TermHeader } from '../../../components/terminal/index.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

const _SETTINGS_PHRASE_KEYS = [
  'settingsPhrase.cuore',
  'settingsPhrase.humanAligned',
  'settingsPhrase.safe',
  'settingsPhrase.navigate',
  'settingsPhrase.compass',
];

export default function SettingsPage({ theme, onOpenGradeFormula, onSharedDisconnected }) {
  const { mode: themeMode, family: themeFamily, onApplyMode, onApplyFamily } = theme;
  const [appVersion, setAppVersion] = useState(null);
  const [settingsPhrase, setSettingsPhrase] = useState('');
  const [providerConfigs, setProviderConfigs] = useState({});

  useEffect(() => {
    setSettingsPhrase(t(_SETTINGS_PHRASE_KEYS[Math.floor(Math.random() * _SETTINGS_PHRASE_KEYS.length)]));
    getHealth().then((d) => setAppVersion(d.version || null)).catch((err) => console.warn('Failed to fetch app version:', err));
    getProviderConfigs().then(setProviderConfigs).catch(() => setProviderConfigs({}));
  }, []);

  return (
    <div className="settings-page settings-page--terminal">
      <TermHeader
        name={t('settings.termName')}
        sub={t('settings.termSub')}
      />
      <div className="settings-grid">
        <ProviderTabs providerConfigs={providerConfigs} />
        <AssistantProviderTabs providerConfigs={providerConfigs} />
        <EvaluationSection />
        <TerminalSection />
        <ServerSection />
        <SharedRepoSection onDisconnected={onSharedDisconnected} />
        <section className="panel settings-section">
          <div className="panel-header">
            <SectionLabel marker="▶">{t('settings.gradeFormula')}</SectionLabel>
          </div>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">{t('settings.gradeFormula')}</span>
              <span className="settings-description">
                {t('settings.gradeFormulaDesc')}
              </span>
            </div>
            <button type="button" className="settings-pill" onClick={onOpenGradeFormula}>
              {t('settings.openEditor')}
            </button>
          </div>
        </section>
        <AppearanceSection themeMode={themeMode} themeFamily={themeFamily} onApplyMode={onApplyMode} onApplyFamily={onApplyFamily} />
        <DesktopSection />
        <UpdatesSection />
        <AboutSection appVersion={appVersion} settingsPhrase={settingsPhrase} />
      </div>
    </div>
  );
}
