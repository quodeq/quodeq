import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { ACTIVE_PROVIDER_KEY, DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT_S, notifyProviderSettingsChanged } from '../../../constants.js';
import useProviderSettings from '../hooks/useProviderSettings.js';
import { classifyProvider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import LlamaCppTab from './LlamaCppTab.jsx';
import OmlxTab from './OmlxTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';

const PROVIDER_HINT = (
  <>
    <p>Quodeq works with several AI providers, but you need to install each one before you can use it.</p>
    <p>For the CLI tools (Claude Code, Codex, Gemini), install them on your machine and they show up here ready to go. Ollama needs to be running locally. Cloud providers like OpenRouter need an API key set up.</p>
    <p>Greyed out tabs below mean that provider isn&apos;t installed yet.</p>
  </>
);

const INSTALL_INSTRUCTIONS = {
  claude: (
    <>
      Install Claude Code from Anthropic&apos;s official documentation, then restart Quodeq. Once <code>claude</code> is on your PATH, this tab will be ready to use.
    </>
  ),
  codex: (
    <>
      Install the OpenAI Codex CLI from the official OpenAI documentation, then restart Quodeq. Once <code>codex</code> is on your PATH, this tab will be ready to use.
    </>
  ),
  gemini: (
    <>
      Install the Gemini CLI from Google&apos;s official documentation, then restart Quodeq. Once <code>gemini</code> is on your PATH, this tab will be ready to use.
    </>
  ),
};

const CLI_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), 'time-limit': String(DEFAULT_TIME_LIMIT_S) };
const OLLAMA_DEFAULTS = { 'time-limit': '0' };
const LLAMACPP_DEFAULTS = { 'time-limit': '0' };
const OMLX_DEFAULTS = { 'time-limit': '0' };
const CLOUD_DEFAULTS_BY_ID = {
  openrouter: { 'time-limit': String(DEFAULT_TIME_LIMIT_S), 'model': 'baidu/cobuddy:free' },
};
const DEFAULT_PROVIDER_ORDER = 50;

const MIGRATION_DONE_KEY = 'cc-provider-tabs-migrated';
const LEGACY_AI_CMD_KEY = 'cc-ai-cmd';
const LEGACY_SETTING_MIGRATIONS = {
  'cc-max-subagents': 'subagents',
  // Legacy global key — migrate to provider-scoped 'time-limit' suffix.
  'cc-pool-budget': 'time-limit',
  'cc-time-limit': 'time-limit',
  'cc-per-dimension': 'per-dimension',
  'cc-ai-model': 'model',
};

function TabContent({ provider, providerConfig }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
  const localApiDefaults = provider.id === 'llamacpp'
    ? LLAMACPP_DEFAULTS
    : provider.id === 'omlx'
      ? OMLX_DEFAULTS
      : OLLAMA_DEFAULTS;
  const defaults = classification === 'cli'
    ? CLI_DEFAULTS
    : classification === 'local-api'
      ? localApiDefaults
      : CLOUD_DEFAULTS_BY_ID[provider.id];
  const { state, update } = useProviderSettings(provider.id, defaults);

  if (classification === 'local-api') {
    if (provider.id === 'llamacpp') {
      return <LlamaCppTab state={state} update={update} />;
    }
    if (provider.id === 'omlx') {
      return <OmlxTab state={state} update={update} />;
    }
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
        const firstInstalled = list.find((c) => c.installed !== false) || list[0];
        setActiveTab(firstInstalled.id);
        localStorage.setItem(ACTIVE_PROVIDER_KEY, firstInstalled.id);
      }
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError('We couldn’t load your AI providers. Make sure the server is running.'); });
  }, []);

  const selectTab = (id) => {
    setActiveTab(id);
    localStorage.setItem(ACTIVE_PROVIDER_KEY, id);
    // The assistant's Default mode follows the analysis provider — tell it to
    // re-read so its displayed provider/model updates live.
    notifyProviderSettingsChanged();
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
          <span className="settings-label-row">
            <span className="settings-label">AI Provider</span>
            <HelpHint label="AI provider help">{PROVIDER_HINT}</HelpHint>
          </span>
          <span className="settings-description">Choose which AI runs your evaluations.</span>
        </div>
        <div className="settings-pill-group" role="tablist">
          {clients.map((c) => {
            const installed = c.installed !== false;
            return (
              <button
                key={c.id}
                type="button"
                role="tab"
                aria-selected={c.id === activeTab}
                aria-disabled={!installed}
                title={installed ? undefined : `${c.label} isn’t installed yet`}
                className={`settings-pill${c.id === activeTab ? ' settings-pill--active' : ''}${installed ? '' : ' settings-pill--disabled'}`}
                onClick={() => selectTab(c.id)}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>
      {active && active.installed === false && (
        <div className="settings-row">
          <div className="settings-install-hint">
            <strong>{active.label} isn&apos;t installed yet.</strong>{' '}
            {INSTALL_INSTRUCTIONS[active.id] || <>Install this provider on your machine and restart Quodeq, and this tab will be ready to use.</>}
          </div>
        </div>
      )}
      {active && active.installed !== false && (
        <div className="provider-tab-content">
          <TabContent key={active.id} provider={active} providerConfig={providerConfigs?.[active.id] || {}} />
        </div>
      )}
    </section>
  );
}
