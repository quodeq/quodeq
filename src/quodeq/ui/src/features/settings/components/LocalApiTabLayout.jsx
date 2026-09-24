/**
 * The frame the local-API provider tabs (Ollama, llama.cpp, MLX) share:
 * server-status pill, the models error, the provider's own model row, the
 * shared time-limit setting and the advanced panel. Only the model row and
 * the provider-specific labels differ, so those are passed in.
 */
import { useId } from 'react';
import ServerStatusPill from '../../../components/ServerStatusPill.jsx';
import { SettingsRowLabel } from './settingsRowParts.jsx';
import { t } from '../../../strings/index.js';
import { TimeLimitSetting } from './ProviderSettings.jsx';
import { LocalApiAdvancedPanel } from './LocalApiAdvancedPanel.jsx';
import { SERVER_STATUS } from '../settingsVocab.js';

/**
 * @param {object} props
 * @param {{status?: string, address?: string}} props.serverStatus  what the status pill shows
 * @param {string} props.offlineMessage  the pill's copy when the server is down
 * @param {() => void} props.onToggleConsole
 * @param {boolean} props.consoleOpen
 * @param {string} props.modelsError  message shown when the model list failed to load
 * @param {React.ReactNode} props.modelRow  the provider's own model picker
 * @param {object} props.state  settings state
 * @param {(patch: object) => void} props.update  settings updater
 * @param {string} props.subagentsDescription
 * @param {string} props.subagentsAriaLabel
 * @param {boolean} props.testDisabled  disables the advanced panel's test action
 * @param {number} props.concurrency
 * @returns {JSX.Element}
 */
export function LocalApiTabLayout({
  serverStatus, offlineMessage, onToggleConsole, consoleOpen, modelsError, modelRow,
  state, update, subagentsDescription, subagentsAriaLabel, testDisabled, concurrency,
}) {
  return (
    <>
      <ServerStatusPill
        status={serverStatus?.status ?? SERVER_STATUS.OFFLINE}
        address={serverStatus?.address}
        offlineMessage={offlineMessage}
        onToggleConsole={onToggleConsole}
        consoleOpen={consoleOpen}
      />
      {modelsError && <div className="settings-row"><span className="settings-error">{modelsError}</span></div>}
      {modelRow}
      <TimeLimitSetting state={state} update={update} providerType="local-api" />
      <LocalApiAdvancedPanel
        subagentsDescription={subagentsDescription}
        subagentsAriaLabel={subagentsAriaLabel}
        state={state}
        update={update}
        testDisabled={testDisabled}
        {...concurrency}
      />
    </>
  );
}

/**
 * The model row on a local-API tab: the model label, the provider's help hint
 * and the shared description, beside the provider's own control.
 * `renderControl(labelId)` is handed the id that names the control.
 */
export function LocalApiModelRow({ hint, renderControl }) {
  const labelId = useId();
  return (
    <div className="settings-row">
      <SettingsRowLabel
        labelId={labelId}
        label={t('settings.modelLabel')}
        hint={hint}
        hintAria={t('settings.modelHelpAria')}
        description={t('settings.thisModelEveryStep')}
      />
      {renderControl(labelId)}
    </div>
  );
}

/**
 * A model row whose control is a picker over the server's models, bound to
 * `state.model`. `Control` is the tab's own picker component; it gets
 * `{ value, models, onChange, labelId }`.
 */
export function LocalApiModelSelectRow({ hint, Control, state, update, models }) {
  return (
    <LocalApiModelRow
      hint={hint}
      renderControl={(labelId) => (
        <Control value={state.model} models={models} onChange={(v) => update('model', v)} labelId={labelId} />
      )}
    />
  );
}

/**
 * The picker over the models a local-API server reports, with the empty
 * "pick a model" entry the tabs rely on to express "nothing chosen yet".
 */
export function ModelPickerSelect({ value, models, onChange, labelId, className }) {
  return (
    <select
      className={className}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-labelledby={labelId}
    >
      <option value="">{t('settings.pickAModel')}</option>
      {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
    </select>
  );
}
