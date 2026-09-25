import useTerminalSettings from '../hooks/useTerminalSettings.js';
import { useTerminalRestart } from '../hooks/useTerminalRestart.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { SettingsPillTabs } from './settingsRowParts.jsx';

export default function TerminalSection() {
  const { enabled, setEnabled } = useTerminalSettings();
  const restart = useTerminalRestart();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">{t('settings.terminalLabel')}</SectionLabel></div>
      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.terminalEnable')}</span>
          <span className="settings-description">
            {t('settings.terminalEnableDesc')}
          </span>
        </div>
        <SettingsPillTabs
          options={[{ v: true, l: t('settings.on') }, { v: false, l: t('settings.off') }]}
          value={enabled}
          onChange={setEnabled}
        />
      </div>
      {enabled && (
        <div className="settings-row settings-row--last">
          <span className="settings-description">
            {t('settings.terminalRestartDesc')}
          </span>
          <button type="button" className="settings-pill" onClick={restart}>
            {t('settings.restartTerminal')}
          </button>
        </div>
      )}
    </section>
  );
}
