import useLiveFeedSettings from '../hooks/useLiveFeedSettings.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';

export default function EvaluationSection() {
  const { newOnly, setNewOnly } = useLiveFeedSettings();
  return (
    <section className="panel settings-section">
      <div className="panel-header"><SectionLabel marker="▶">{t('settings.evaluationLabel')}</SectionLabel></div>
      <div className="settings-row settings-row--last">
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.liveFindings')}</span>
          <span className="settings-description">
            {t('settings.liveFindingsDesc')}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ v: true, l: t('settings.liveFindingsNewOnly') }, { v: false, l: t('evaluate.allCap') }].map(({ v, l }) => (
            <button key={l} type="button" role="tab" aria-selected={newOnly === v}
              className={`settings-pill${newOnly === v ? ' settings-pill--active' : ''}`}
              onClick={() => setNewOnly(v)}>{l}</button>
          ))}
        </div>
      </div>
    </section>
  );
}
