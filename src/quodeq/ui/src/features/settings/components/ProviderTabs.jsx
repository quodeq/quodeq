import { useState, useEffect } from 'react';
import { getAiClients, getOllamaStatus } from '../../../api/index.js';
import { ACTIVE_PROVIDER_KEY } from '../../../constants.js';
import useProviderSettings from '../hooks/useProviderSettings.js';
import { classify_provider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';

const CLI_DEFAULTS = { 'subagents': '5' };

function TabContent({ provider, providerConfig }) {
  const classification = classify_provider(provider.id, provider.type, providerConfig);
  const defaults = classification === 'cli' ? CLI_DEFAULTS : undefined;
  const { state, update } = useProviderSettings(provider.id, defaults);

  if (classification === 'local-api') {
    return <OllamaTab state={state} update={update} />;
  }
  if (classification === 'cli') {
    return <CliProviderTab providerId={provider.id} state={state} update={update} />;
  }
  return <CloudProviderTab providerId={provider.id} providerConfig={providerConfig} state={state} update={update} />;
}

export default function ProviderTabs({ providerConfigs }) {
  const [clients, setClients] = useState([]);
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(ACTIVE_PROVIDER_KEY) || '');
  const [statuses, setStatuses] = useState({});

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      // Sort by 'order' field from provider configs (ai_providers.json)
      const list = [...raw].sort((a, b) => {
        const oa = providerConfigs?.[a.id]?.order ?? 50;
        const ob = providerConfigs?.[b.id]?.order ?? 50;
        return oa - ob;
      });
      setClients(list);
      if (!activeTab && list.length > 0) {
        setActiveTab(list[0].id);
        localStorage.setItem(ACTIVE_PROVIDER_KEY, list[0].id);
      }

      // Migrate old global settings to active provider
      const MIGRATION_KEY = 'cc-provider-tabs-migrated';
      if (!localStorage.getItem(MIGRATION_KEY) && list.length > 0) {
        const targetId = localStorage.getItem('cc-ai-cmd') || list[0].id;
        const migrations = {
          'cc-max-subagents': 'subagents',
          'cc-pool-budget': 'pool-budget',
          'cc-per-dimension': 'per-dimension',
          'cc-ai-model': 'model',
        };
        for (const [oldKey, newSuffix] of Object.entries(migrations)) {
          const oldVal = localStorage.getItem(oldKey);
          if (oldVal !== null) {
            localStorage.setItem(`cc-${targetId}-${newSuffix}`, oldVal);
            localStorage.removeItem(oldKey);
          }
        }
        localStorage.setItem(MIGRATION_KEY, '1');
      }
    }).catch(() => setClients([]));
  }, []);

  useEffect(() => {
    const ollama = clients.find((c) => c.id === 'ollama');
    if (ollama) {
      getOllamaStatus()
        .then((s) => setStatuses((prev) => ({ ...prev, ollama: s.running })))
        .catch(() => setStatuses((prev) => ({ ...prev, ollama: false })));
    }
  }, [clients]);

  const selectTab = (id) => {
    setActiveTab(id);
    localStorage.setItem(ACTIVE_PROVIDER_KEY, id);
  };

  const active = clients.find((c) => c.id === activeTab);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <h2 className="settings-section-title">Analysis</h2>
      </div>
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">AI Provider</span>
          <span className="settings-description">Select the AI provider used when running evaluations</span>
        </div>
        <div className="provider-tab-bar">
          {clients.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`provider-tab${c.id === activeTab ? ' provider-tab--active' : ''}`}
              onClick={() => selectTab(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>
      {active && (
        <div className="provider-tab-content">
          <TabContent key={active.id} provider={active} providerConfig={providerConfigs?.[active.id] || {}} />
        </div>
      )}
    </section>
  );
}
