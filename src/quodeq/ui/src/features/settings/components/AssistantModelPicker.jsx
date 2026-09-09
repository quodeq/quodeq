import { useQuery } from '@tanstack/react-query';
import { useApi } from '../../../api/ApiContext.jsx';
import { settingsKeys } from '../../../api/queryKeys.js';
import { classifyProvider } from './providerUtils.js';
import { ModelTextInput } from './CliAdvancedPanel.jsx';
import { t } from '../../../strings/index.js';

const LOCAL_API_CONFIG = {
  ollama: { apiFn: 'getOllamaModels', queryKey: settingsKeys.ollamaModels(), errorLabel: 'Ollama' },
  llamacpp: { apiFn: 'getLlamacppModels', queryKey: settingsKeys.llamacppModels(), errorLabel: 'llama.cpp' },
  omlx: { apiFn: 'getOmlxModels', queryKey: settingsKeys.omlxModels(), errorLabel: 'MLX' },
};

// A <select> of installed models for local-api providers, mirroring OllamaTab's
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
      <select
        className={`settings-model-input${value ? '' : ' settings-model-input--required'}`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={t('settings.assistantModelAria')}
      >
        <option value="">{t('settings.pickAModel')}</option>
        {models.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
      </select>
      {error && (
        <span className="settings-error">
          {t('settings.localApiModelsLoadFailed', { provider: cfg.errorLabel })}
        </span>
      )}
    </div>
  );
}

// Mirrors the evaluation's per-provider model widget: a dropdown of installed
// models for local-api providers, a free-text model id for cli / cloud-api.
// ariaLabel keeps this picker's own accessible name now that the text input
// is CliAdvancedPanel's shared ModelTextInput rather than a local copy.
export default function AssistantModelPicker({ provider, providerConfig, value, onChange }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
  if (classification === 'local-api') {
    return <LocalApiModelSelect providerId={provider.id} value={value} onChange={onChange} />;
  }
  return <ModelTextInput value={value} onChange={onChange} ariaLabel={t('settings.assistantModelAria')} />;
}
