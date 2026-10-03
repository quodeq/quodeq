/**
 * The pieces every settings row is assembled from.
 *
 * Each row is a label block (label, optional help hint, description) beside a
 * control. The controls stay with their tabs because that is where they
 * actually differ.
 */
import { MIN_SUBAGENTS, MAX_SUBAGENTS, PROVIDER_SETTING_KEY } from '../../../constants.js';
import HelpHint from '../../../components/HelpHint.jsx';
import { SUBAGENTS_HINT_REMOTE } from './subagentsHints.jsx';
import { t } from '../../../strings/index.js';

/**
 * A settings row's label block: the label, an optional help hint beside it,
 * and the description underneath. `labelId` labels the row's control through
 * aria-labelledby when the control has no label of its own. Rows that never
 * carry a hint pass `hintSlot={false}` and get the label without the hint
 * row around it.
 */
export function SettingsRowLabel({ label, hint, hintAria, description, labelId, hintSlot = true }) {
  if (!hintSlot) {
    return (
      <div className="settings-row-label">
        <span className="settings-label" id={labelId}>{label}</span>
        <span className="settings-description">{description}</span>
      </div>
    );
  }
  return (
    <div className="settings-row-label">
      <span className="settings-label-row">
        <span className="settings-label" id={labelId}>{label}</span>
        {hint && <HelpHint label={hintAria}>{hint}</HelpHint>}
      </span>
      <span className="settings-description">{description}</span>
    </div>
  );
}

/**
 * The max-parallel-agents row the remote (CLI and cloud) provider tabs share.
 * `clampSubagents` commits the entry on blur, and differs per tab only in
 * what it falls back to.
 */
export function RemoteSubagentsRow({ state, update, clampSubagents }) {
  return (
    <div className="settings-row">
      <SettingsRowLabel
        label={t('settings.maxParallelAgents')}
        hint={SUBAGENTS_HINT_REMOTE}
        hintAria={t('settings.maxParallelAgentsHelpAria')}
        description={t('settings.subagentsDescRemote')}
      />
      <input
        type="number"
        className="settings-model-input"
        min={MIN_SUBAGENTS}
        max={MAX_SUBAGENTS}
        value={state.subagents ?? ''}
        onChange={(e) => update(PROVIDER_SETTING_KEY.SUBAGENTS, e.target.value)}
        onBlur={(e) => { if (e.target.value !== '') update(PROVIDER_SETTING_KEY.SUBAGENTS, clampSubagents(e.target.value)); }}
        aria-label={t('settings.maxParallelAgents')}
      />
    </div>
  );
}

/**
 * A pill group presented as a tablist: one pill per option, the pill matching
 * `value` marked selected. `options` are `{ v, l }` value/label pairs.
 */
export function SettingsPillTabs({ options, value, onChange }) {
  return (
    <div className="settings-pill-group" role="tablist">
      {options.map(({ v, l }) => (
        <button key={l} type="button" role="tab" aria-selected={value === v}
          className={`settings-pill${value === v ? ' settings-pill--active' : ''}`}
          onClick={() => onChange(v)}>{l}</button>
      ))}
    </div>
  );
}

/**
 * An on/off pill pair for a boolean setting, as two pressed-state toggles.
 */
export function SettingsOnOffPills({ on, onToggle }) {
  return (
    <div className="settings-pill-group">
      <button
        type="button"
        className={`settings-pill${on ? ' settings-pill--active' : ''}`}
        onClick={() => onToggle(true)}
        aria-pressed={on}
      >
        {t('settings.on')}
      </button>
      <button
        type="button"
        className={`settings-pill${!on ? ' settings-pill--active' : ''}`}
        onClick={() => onToggle(false)}
        aria-pressed={!on}
      >
        {t('settings.off')}
      </button>
    </div>
  );
}

/**
 * The collapsed "Advanced" block at the foot of a provider tab.
 */
export function SettingsAdvanced({ children }) {
  return (
    <details className="settings-advanced">
      <summary className="settings-advanced-toggle">{t('settings.advanced')}</summary>
      <div className="settings-advanced-content">
        {children}
      </div>
    </details>
  );
}

/**
 * A section's on/off switch row. While the feature is off nothing follows it,
 * so it is the section's last row.
 */
export function SettingsEnableRow({ enabled, setEnabled, label, description }) {
  return (
    <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
      <SettingsRowLabel hintSlot={false} label={label} description={description} />
      <SettingsPillTabs
        options={[{ v: true, l: t('settings.on') }, { v: false, l: t('settings.off') }]}
        value={enabled}
        onChange={setEnabled}
      />
    </div>
  );
}
