import useTerminalSettings from '../hooks/useTerminalSettings.js';
import { useTerminalRestart } from '../hooks/useTerminalRestart.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { SettingsEnableRow } from './settingsRowParts.jsx';

export default function TerminalSection() {
  const { enabled, setEnabled } = useTerminalSettings();
  const restart = useTerminalRestart();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">{t('settings.terminalLabel')}</SectionLabel></div>
      <SettingsEnableRow
        enabled={enabled}
        setEnabled={setEnabled}
        label={t('settings.terminalEnable')}
        description={t('settings.terminalEnableDesc')}
      />
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
