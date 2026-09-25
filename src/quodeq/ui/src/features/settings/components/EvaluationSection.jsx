import useLiveFeedSettings from '../hooks/useLiveFeedSettings.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { SettingsPillTabs, SettingsRowLabel } from './settingsRowParts.jsx';

export default function EvaluationSection() {
  const { newOnly, setNewOnly } = useLiveFeedSettings();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">{t('settings.evaluationLabel')}</SectionLabel></div>
      <div className="settings-row settings-row--last">
        <SettingsRowLabel hintSlot={false} label={t('settings.liveFindings')} description={t('settings.liveFindingsDesc')} />
        <SettingsPillTabs
          options={[{ v: true, l: t('settings.liveFindingsNewOnly') }, { v: false, l: t('evaluate.allCap') }]}
          value={newOnly}
          onChange={setNewOnly}
        />
      </div>
    </section>
  );
}
