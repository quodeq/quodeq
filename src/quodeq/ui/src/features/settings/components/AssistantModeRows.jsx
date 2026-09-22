import { t } from '../../../strings/index.js';

const MODE_OPTIONS = [
  { value: 'default', label: t('settings.modeDefault') },
  { value: 'custom', label: t('settings.modeCustom') },
];

/**
 * AssistantProviderTabs.jsx's "model source" mode picker + the default-mode
 * "follows analysis" summary row. Extracted verbatim.
 */
export function AssistantModeRows({ enabled, mode, setMode, active, activeProvider, model }) {
  return (
    <>
      {enabled && (
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">{t('settings.modelSource')}</span>
          <span className="settings-description">
            {t('settings.modelSourceDesc')}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {MODE_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              className={`settings-pill${mode === value ? ' settings-pill--active' : ''}`}
              onClick={() => setMode(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      )}

      {enabled && mode === 'default' && (
        <div className="settings-row settings-row--last">
          <span className="settings-description">
            {t('settings.followsAnalysis', {
              provider: active?.label || activeProvider || t('settings.noneSelected'),
              model: model || t('settings.modeDefault').toLowerCase(),
            })}
          </span>
        </div>
      )}
    </>
  );
}
