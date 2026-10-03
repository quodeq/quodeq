import { t } from '../../../strings/index.js';
import { ASSISTANT_MODE } from '../settingsVocab.js';
import { SettingsRowLabel } from './settingsRowParts.jsx';

const MODE_OPTIONS = [
  { value: ASSISTANT_MODE.DEFAULT, label: t('settings.modeDefault') },
  { value: ASSISTANT_MODE.CUSTOM, label: t('settings.modeCustom') },
];

/**
 * The assistant's "model source" mode picker, plus the summary row that shows
 * which analysis provider and model the default mode follows.
 */
export function AssistantModeRows({ enabled, mode, setMode, active, activeProvider, model }) {
  return (
    <>
      {enabled && (
      <div className="settings-row">
        <SettingsRowLabel hintSlot={false} label={t('settings.modelSource')} description={t('settings.modelSourceDesc')} />
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

      {enabled && mode === ASSISTANT_MODE.DEFAULT && (
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
