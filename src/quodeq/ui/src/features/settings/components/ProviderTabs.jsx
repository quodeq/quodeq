import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { ACTIVE_PROVIDER_KEY, DEFAULT_MAX_SUBAGENTS, DEFAULT_POOL_BUDGET } from '../../../constants.js';
import useProviderSettings from '../hooks/useProviderSettings.js';
import { classifyProvider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

const CLI_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), 'pool-budget': String(DEFAULT_POOL_BUDGET) };
const DEFAULT_PROVIDER_ORDER = 50;

const MIGRATION_DONE_KEY = 'cc-provider-tabs-migrated';
const LEGACY_AI_CMD_KEY = 'cc-ai-cmd';
const LEGACY_SETTING_MIGRATIONS = {
  'cc-max-subagents': 'subagents',
  'cc-pool-budget': 'pool-budget',
  'cc-per-dimension': 'per-dimension',
  'cc-ai-model': 'model',
};

function TabContent({ provider, providerConfig }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
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

function useMigrateLegacySettings(clients) {
  useEffect(() => {
    if (clients.length === 0) return;
    if (localStorage.getItem(MIGRATION_DONE_KEY)) return;
    const targetId = localStorage.getItem(LEGACY_AI_CMD_KEY) || clients[0].id;
    for (const [oldKey, newSuffix] of Object.entries(LEGACY_SETTING_MIGRATIONS)) {
      const oldVal = localStorage.getItem(oldKey);
      if (oldVal !== null) {
        localStorage.setItem(`cc-${targetId}-${newSuffix}`, oldVal);
        localStorage.removeItem(oldKey);
      }
    }
    localStorage.setItem(MIGRATION_DONE_KEY, '1');
  }, [clients]);
}

export default function ProviderTabs({ providerConfigs }) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem(ACTIVE_PROVIDER_KEY) || '');

  useMigrateLegacySettings(clients);

  useEffect(() => {
    getAiClients().then((data) => {
      const raw = data.clients || [];
      // Sort by 'order' field from provider configs (ai_providers.json)
      const list = [...raw].sort((a, b) => {
        const oa = providerConfigs?.[a.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        const ob = providerConfigs?.[b.id]?.order ?? DEFAULT_PROVIDER_ORDER;
        return oa - ob;
      });
      setClients(list);
      if (!activeTab && list.length > 0) {
        setActiveTab(list[0].id);
        localStorage.setItem(ACTIVE_PROVIDER_KEY, list[0].id);
      }
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError('Failed to load AI providers. Check that the server is running.'); });
  }, []);

  const selectTab = (id) => {
    setActiveTab(id);
    localStorage.setItem(ACTIVE_PROVIDER_KEY, id);
  };

  const active = clients.find((c) => c.id === activeTab);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">Analysis</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label">AI Provider</span>
          <span className="settings-description">Select the AI provider used when running evaluations</span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {clients.map((c) => (
            <button
              key={c.id}
              type="button"
              role="tab"
              aria-selected={c.id === activeTab}
              className={`settings-pill${c.id === activeTab ? ' settings-pill--active' : ''}`}
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
