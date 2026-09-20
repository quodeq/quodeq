import { useId } from 'react';
import { useCopilotModels } from '../hooks/useCopilotModels.js';
import { t } from '../../../strings/index.js';
import CopilotSetupHint from './CopilotSetupHint.jsx';

// Copilot's "let the service pick" entry; it needs a spelled-out label in the
// dropdown, every other id renders as itself.
const AUTO_MODEL_ID = 'auto';

/** Login help is only needed when the live account-model lookup fails. */
export function CopilotModelStatus() {
  const { error, refetch, isFetching } = useCopilotModels();
  if (!error) return null;
  return (
    <CopilotSetupHint>
      <div className="settings-model-field">
        <span className="settings-error" role="alert">
          {t('settings.copilotModelsFailed', { message: error.message })}
        </span>
        <button type="button" className="settings-action-btn" onClick={() => refetch()} disabled={isFetching}>
          {t('common.retryConnection')}
        </button>
      </div>
    </CopilotSetupHint>
  );
}

export default function CopilotModelSelect({ label, value, onChange, required, ariaLabel, placeholder }) {
  const inputId = useId();
  const { data: models = [], isPending } = useCopilotModels();
  const savedModel = value && !models.includes(value);
  return (
    <div className="settings-model-field">
      {label && <label className="settings-model-label" htmlFor={inputId}>{label}</label>}
      <select
        id={inputId}
        className={`settings-model-input${required && !value ? ' settings-model-input--required' : ''}`}
        value={value || ''}
        onChange={(event) => onChange(event.target.value)}
        aria-label={ariaLabel || (label ? t('settings.modelNameAria', { label }) : t('settings.modelAria'))}
        disabled={!models.length}
      >
        <option value="">{placeholder || t('settings.pickAModel')}</option>
        {savedModel && <option value={value} disabled>{t('settings.copilotSavedModel', { model: value })}</option>}
        {models.map((model) => (
          <option key={model} value={model}>{model === AUTO_MODEL_ID ? t('settings.copilotAutoModel') : model}</option>
        ))}
      </select>
      {isPending && <span className="settings-model-hint" role="status">{t('settings.copilotModelsLoading')}</span>}
    </div>
  );
}
