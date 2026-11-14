import { useId, useState } from 'react';
import { useClientModels, findCatalogModel } from '../hooks/useClientModels.js';
import { t } from '../../../strings/index.js';
import Select from '../../../components/select/Select.jsx';

// The select value that switches the field to a typed model id.
const OTHER_VALUE = '__other__';

function modelInputClass(required, value) {
  return `settings-model-input${required && !value ? ' settings-model-input--required' : ''}`;
}

function optionLabel(entry) {
  return entry.isDefault ? t('settings.modelRecommended', { label: entry.label }) : entry.label;
}

function modelOptions(catalog) {
  const toOptions = (entries) => entries.map((entry) => ({ value: entry.id, label: optionLabel(entry) }));
  const latest = catalog.filter((entry) => !entry.pinned);
  const pinned = catalog.filter((entry) => entry.pinned);
  if (!pinned.length) return toOptions(latest);
  return [
    { group: t('settings.modelGroupLatest'), options: toOptions(latest) },
    { group: t('settings.modelGroupPinned'), options: toOptions(pinned) },
  ];
}

function RefreshButton({ onRefresh, busy }) {
  return (
    <button
      type="button" className="settings-action-btn settings-model-refresh" onClick={onRefresh} disabled={busy}
      aria-label={t('settings.refreshModels')} title={t('settings.refreshModels')}
    >
      ↻
    </button>
  );
}

function TypedModelInput({ inputId, value, onChange, required, ariaLabel }) {
  return (
    <input
      type="text" id={inputId}
      className={modelInputClass(required, value)}
      value={value || ''} placeholder={t('settings.typeModelId')} onChange={(e) => onChange(e.target.value)}
      aria-label={ariaLabel || t('settings.modelAria')}
      autoCapitalize="off" autoCorrect="off" autoComplete="off" spellCheck={false}
    />
  );
}

/**
 * The model field for a CLI that lists its own models (Claude Code, Codex):
 * a dropdown of what the signed-in account offers, with the selected model's
 * description under it. "Other model id" keeps a typed id possible, and a
 * failed lookup falls back to the plain text field.
 */
export default function CliModelPicker({ providerId, value, onChange, required, ariaLabel }) {
  const inputId = useId();
  const { data: catalog, isPending, error, isFetching, refresh } = useClientModels(providerId);
  const listed = findCatalogModel(catalog, value);
  const [typing, setTyping] = useState(false);
  const typed = typing || Boolean(value && catalog && !listed);
  // The query's own error state shows a failed refresh; this only logs it.
  const onRefresh = () => refresh().catch((err) => console.warn('[CliModelPicker] model list refresh failed:', err));

  if (error) {
    return (
      <div className="settings-model-field settings-model-field--picker">
        <div className="settings-model-select-row">
          <TypedModelInput inputId={inputId} value={value} onChange={onChange} required={required} ariaLabel={ariaLabel} />
          <RefreshButton onRefresh={onRefresh} busy={isFetching} />
        </div>
        <span className="settings-description" role="status">{t('settings.modelsUnavailable')}</span>
      </div>
    );
  }

  function choose(next) {
    setTyping(next === OTHER_VALUE);
    if (next !== OTHER_VALUE) onChange(next);
  }

  return (
    <div className="settings-model-field settings-model-field--picker">
      <div className="settings-model-select-row">
        <Select
          id={inputId}
          className={modelInputClass(required, value)}
          value={typed ? OTHER_VALUE : (value || '')}
          onChange={choose}
          aria-label={ariaLabel || t('settings.modelAria')}
          disabled={isPending}
          options={[
            { value: '', label: isPending ? t('settings.modelsLoading') : t('settings.pickAModel'), disabled: true },
            ...(catalog ? modelOptions(catalog) : []),
            { value: OTHER_VALUE, label: t('settings.otherModelId') },
          ]}
        />
        <RefreshButton onRefresh={onRefresh} busy={isFetching} />
      </div>
      {typed && <TypedModelInput value={value} onChange={onChange} required={required} ariaLabel={t('settings.otherModelId')} />}
      {listed?.description && <span className="settings-description">{listed.description}</span>}
    </div>
  );
}
