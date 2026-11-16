import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { settingsKeys } from '../../../api/queryKeys.js';
import { classifyProvider, PROVIDER_CLASSIFICATION } from './providerUtils.js';
import { CliModelInput } from './CliProviderRows.jsx';
import { t } from '../../../strings/index.js';
import { ModelPickerSelect } from './LocalApiTabLayout.jsx';

const LOCAL_API_CONFIG = {
  ollama: { apiFn: 'getOllamaModels', queryKey: settingsKeys.ollamaModels(), errorLabel: 'Ollama' },
  llamacpp: { apiFn: 'getLlamacppModels', queryKey: settingsKeys.llamacppModels(), errorLabel: 'llama.cpp' },
  omlx: { apiFn: 'getOmlxModels', queryKey: settingsKeys.omlxModels(), errorLabel: 'MLX' },
};

// The installed models for local-api providers, mirroring OllamaTab's
// ModelSelector. Fetches via the provider-specific api fn from useApi().
function LocalApiModelSelect({ providerId, value, onChange }) {
  const api = useApi();
  const cfg = LOCAL_API_CONFIG[providerId] || LOCAL_API_CONFIG.ollama;
  const { data: models = [], error } = useQuery({
    queryKey: cfg.queryKey,
    queryFn: () => api[cfg.apiFn](),
  });
  return (
    <div className="settings-model-field">
      <ModelPickerSelect
        className={`settings-model-input${value ? '' : ' settings-model-input--required'}`}
        value={value}
        models={models}
        onChange={onChange}
        ariaLabel={t('settings.assistantModelAria')}
      />
      {error && (
        <span className="settings-error">
          {t('settings.localApiModelsLoadFailed', { provider: cfg.errorLabel })}
        </span>
      )}
    </div>
  );
}

// Mirrors the evaluation's per-provider model widget: a dropdown of installed
// models for local-api and Copilot providers, a model id for other providers.
export default function AssistantModelPicker({ provider, providerConfig, value, onChange }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
  if (classification === PROVIDER_CLASSIFICATION.LOCAL_API) {
    return <LocalApiModelSelect providerId={provider.id} value={value} onChange={onChange} />;
  }
  return <CliModelInput providerId={provider.id} value={value} onChange={onChange} ariaLabel={t('settings.assistantModelAria')} />;
}
