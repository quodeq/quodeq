import { useId } from 'react';
import { CliModelInput } from '../../settings/components/CliProviderRows.jsx';
import { ModelPickerSelect } from '../../settings/components/LocalApiTabLayout.jsx';
import { modelEffort, useClientModels } from '../../settings/hooks/useClientModels.js';
import { useOllamaModels } from '../../settings/hooks/useOllamaModels.js';
import { defaultEffortLabel, effortLabel } from '../../settings/effortLabels.js';
import { PROVIDER } from '../../../vocab/provider.js';
import { t } from '../../../strings/index.js';
import Select from '../../../components/select/Select.jsx';

function OllamaModelField({ value, onChange }) {
  const labelId = useId();
  const { models } = useOllamaModels();
  return (
    <div className="settings-model-field">
      <span id={labelId} className="sr-only">{t('settings.modelAria')}</span>
      <ModelPickerSelect
        className={`settings-model-input${value ? '' : ' settings-model-input--required'}`}
        value={value || ''} models={models} onChange={onChange} labelId={labelId}
      />
    </div>
  );
}

/** The model's effort as a select: Default (naming the model's own), then its levels. */
function EffortSelect({ providerId, model, effort, onEffort }) {
  const { data: catalog } = useClientModels(providerId);
  const { levels, defaultEffort } = modelEffort(catalog, model);
  if (!levels.length) return null;
  return (
    <Select
      className="settings-model-input reviewer-fields__effort" aria-label={t('settings.effort')}
      value={levels.includes(effort) ? effort : ''} onChange={onEffort}
      options={[
        { value: '', label: defaultEffortLabel(defaultEffort) },
        ...levels.map((level) => ({ value: level, label: effortLabel(level) })),
      ]}
    />
  );
}

/**
 * The model and effort fields for one provider (server id): the live catalog
 * picker for a CLI that lists its models, Ollama's installed models, a typed
 * model id otherwise. Effort shows only where the model takes one.
 */
export default function ReviewerFields({ providerId, model, effort, onModel, onEffort }) {
  return (
    <div className="reviewer-fields">
      {providerId === PROVIDER.OLLAMA
        ? <OllamaModelField value={model} onChange={onModel} />
        : <CliModelInput providerId={providerId} value={model} onChange={onModel} required />}
      <EffortSelect providerId={providerId} model={model} effort={effort} onEffort={onEffort} />
    </div>
  );
}
