import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import useAssistantProvider from '../hooks/useAssistantProvider.js';
import AssistantModelPicker from './AssistantModelPicker.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

const DEFAULT_PROVIDER_ORDER = 50;

const MODE_OPTIONS = [
  { value: 'default', label: 'Default' },
  { value: 'custom', label: 'Custom' },
];

export default function AssistantProviderTabs({ providerConfigs }) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const { enabled, setEnabled, mode, setMode, activeProvider, setActiveProvider, model, setModel } = useAssistantProvider();

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

      <div className={`settings-row${enabled ? '' : ' settings-row--last'}`}>
        <div className="settings-row-label">
          <span className="settings-label">Enable assistant</span>
          <span className="settings-description">
            Shows the assistant button (✦) in the toolbar and enables the Ctrl+` panel. On by default.
          </span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {[{ value: true, label: 'On' }, { value: false, label: 'Off' }].map(({ value, label }) => (
            <button
              key={label}
              type="button"
              role="tab"
              aria-selected={enabled === value}
              className={`settings-pill${enabled === value ? ' settings-pill--active' : ''}`}
              onClick={() => setEnabled(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {enabled && (
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">Model source</span>
          <span className="settings-description">
            Default follows your Analysis provider and model. Choose Custom to pick a different one for the assistant.
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
            Follows Analysis · {active?.label || activeProvider || 'none selected'} · {model || 'default'}
          </span>
        </div>
      )}

      {enabled && mode === 'custom' && (
        <>
          <div className="settings-row">
            <div className="settings-row-label">
              <span className="settings-label">AI Provider</span>
              <span className="settings-description">Choose which AI powers the in-app assistant.</span>
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
                <span className="settings-description">Pick the model the assistant should use.</span>
              </div>
              <AssistantModelPicker
                provider={active}
                providerConfig={providerConfigs?.[active.id] || {}}
                value={model}
                onChange={setModel}
              />
            </div>
          )}
        </>
      )}
    </section>
  );
}
