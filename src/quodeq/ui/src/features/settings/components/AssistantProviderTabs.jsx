import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import useAssistantProvider from '../hooks/useAssistantProvider.js';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

const DEFAULT_PROVIDER_ORDER = 50;

export default function AssistantProviderTabs({ providerConfigs }) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const { activeProvider, setActiveProvider, model, setModel, followsAnalysis } = useAssistantProvider();

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      const list = [...raw].sort((a, b) => {
        const oa = providerConfigs?.[a.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        const ob = providerConfigs?.[b.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        return oa - ob;
      });
      setClients(list);
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError('We couldn’t load your AI providers. Make sure the server is running.'); });
  }, []);

  const active = clients.find((c) => c.id === activeProvider);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">Assistant</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">AI Provider</span>
          <span className="settings-description">
            Choose which AI powers the in-app assistant.
            {followsAnalysis && <> Currently follows the Analysis provider.</>}
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {clients.map((c) => {
            const installed = c.installed !== false;
            return (
              <button
                key={c.id}
                type="button"
                role="tab"
                aria-selected={c.id === activeProvider}
                aria-disabled={!installed}
                title={installed ? undefined : `${c.label} isn’t installed yet`}
                className={`settings-pill${c.id === activeProvider ? ' settings-pill--active' : ''}${installed ? '' : ' settings-pill--disabled'}`}
                onClick={() => setActiveProvider(c.id)}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>
      {active && (
        <div className="settings-row settings-row--last">
          <div className="settings-row-label">
            <span className="settings-label">Model</span>
            <span className="settings-description">
              Override the model used by the assistant. Leave blank to use the Analysis model.
            </span>
          </div>
          <input
            type="text"
            className="settings-model-input"
            value={model}
            placeholder="default"
            onChange={(e) => setModel(e.target.value)}
            aria-label="Assistant model override"
            autoCapitalize="off"
            autoCorrect="off"
            autoComplete="off"
            spellCheck={false}
          />
        </div>
      )}
    </section>
  );
}
