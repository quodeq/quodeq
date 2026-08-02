import { t } from '../../../strings/index.js';

const MODE_OPTIONS = [
  { value: 'system',   label: t('settings.themeModeSystem') },
  { value: 'light',    label: t('settings.themeModeLight') },
  { value: 'dark',     label: t('settings.themeModeDark') },
];

// Theme family names are product identity (each palette has a proper name),
// not translatable prose.
const FAMILY_OPTIONS = [
  { value: 'daruma',    label: 'Daruma' },
  { value: 'neo',       label: 'Neo' },
  { value: 'ifrit',     label: 'Ifrit' },
  { value: 'deckard',   label: 'Deckard' },
  { value: 'galadriel', label: 'Galadriel' },
];

import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

export default function AppearanceSection({ themeMode, themeFamily, onApplyMode, onApplyFamily }) {
  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.appearanceLabel')}</SectionLabel>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.modeLabel')}</span>
          <span className="settings-description">{t('settings.modeDesc')}</span>
        </div>
        <div className="settings-pill-group">
          {MODE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`settings-pill${themeMode === value ? ' settings-pill--active' : ''}`}
              onClick={() => onApplyMode(value)}
              aria-pressed={themeMode === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.themeLabel')}</span>
          <span className="settings-description">{t('settings.themeDesc')}</span>
        </div>
        <div className="settings-pill-group">
          {FAMILY_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`settings-pill${themeFamily === value ? ' settings-pill--active' : ''}`}
              onClick={() => onApplyFamily(value)}
              aria-pressed={themeFamily === value}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
