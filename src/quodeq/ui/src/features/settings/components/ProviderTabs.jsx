import { useState, useEffect } from 'react';
import { useApi } from '../../../api/ApiContext.jsx';
import { ACTIVE_PROVIDER_KEY, DEFAULT_MAX_SUBAGENTS, DEFAULT_TIME_LIMIT_S, notifyProviderSettingsChanged } from '../../../constants.js';
import useProviderSettings from '../hooks/useProviderSettings.js';
import { useMigrateLegacySettings } from '../hooks/useMigrateLegacySettings.js';
import { classifyProvider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import LlamaCppTab from './LlamaCppTab.jsx';
import OmlxTab from './OmlxTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';
import { readString, writeString } from '../../../adapters/storage.js';

const PROVIDER_HINT = (
  <>
    <p>{t('settings.providerHintP1')}</p>
    <p>{t('settings.providerHintP2')}</p>
    <p>{t('settings.providerHintP3')}</p>
  </>
);

const INSTALL_INSTRUCTIONS = {
  claude: tRich('settings.installHintClaude'),
  codex: tRich('settings.installHintCodex'),
  gemini: tRich('settings.installHintGemini'),
};

const CLI_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), 'time-limit': String(DEFAULT_TIME_LIMIT_S) };
const OLLAMA_DEFAULTS = { 'time-limit': '0' };
const LLAMACPP_DEFAULTS = { 'time-limit': '0' };
const OMLX_DEFAULTS = { 'time-limit': '0' };
// Every cloud provider runs with the CLI-style effective defaults
// (5 subagents / 600s — see resolveProviderSettings); the tab must display
// them for unset keys or Settings claims values the run won't use.
const CLOUD_FALLBACK_DEFAULTS = { 'subagents': String(DEFAULT_MAX_SUBAGENTS), 'time-limit': String(DEFAULT_TIME_LIMIT_S) };
const CLOUD_DEFAULTS_BY_ID = {
  openrouter: { 'model': 'baidu/cobuddy:free' },
};
const DEFAULT_PROVIDER_ORDER = 50;

/**
 * Display defaults for a provider tab: what an unset key effectively runs
 * with. Exported so tests can pin display == payload.
 */
export function defaultsForProvider(classification, providerId) {
  // The launch command defaults to the provider id itself; the Advanced
  // field shows it pre-filled so changing it is an edit, not a discovery.
  if (classification === 'cli') return { ...CLI_DEFAULTS, 'cmd-path': providerId };
  if (classification === 'local-api') {
    if (providerId === 'llamacpp') return LLAMACPP_DEFAULTS;
    if (providerId === 'omlx') return OMLX_DEFAULTS;
    return OLLAMA_DEFAULTS;
  }
  return { ...CLOUD_FALLBACK_DEFAULTS, ...(CLOUD_DEFAULTS_BY_ID[providerId] || {}) };
}

function TabContent({ provider, providerConfig }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
  const defaults = defaultsForProvider(classification, provider.id);
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

export default function ProviderTabs({ providerConfigs }) {
  const { getAiClients } = useApi();
  const [clients, setClients] = useState([]);
  const [clientsError, setClientsError] = useState(null);
  const [activeTab, setActiveTab] = useState(() => readString(ACTIVE_PROVIDER_KEY) || '');

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
        writeString(ACTIVE_PROVIDER_KEY, firstInstalled.id);
      }
      setClientsError(null);
    }).catch(() => { setClients([]); setClientsError(t('settings.providersLoadFailed')); });
  }, []);

  const selectTab = (id) => {
    setActiveTab(id);
    writeString(ACTIVE_PROVIDER_KEY, id);
    // The assistant's Default mode follows the analysis provider — tell it to
    // re-read so its displayed provider/model updates live.
    notifyProviderSettingsChanged();
  };

  const active = clients.find((c) => c.id === activeTab);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.analysisLabel')}</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}
      <div className="settings-row">
        <div className="settings-row-label">
          <span className="settings-label-row">
            <span className="settings-label">{t('settings.aiProvider')}</span>
            <HelpHint label={t('settings.aiProviderHelpAria')}>{PROVIDER_HINT}</HelpHint>
          </span>
          <span className="settings-description">{t('settings.providerRunsDesc')}</span>
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
                title={installed ? undefined : t('settings.providerNotInstalledTitle', { name: c.label })}
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
            <strong>{t('settings.providerNotInstalled', { name: active.label })}</strong>{' '}
            {INSTALL_INSTRUCTIONS[active.id] || t('settings.installGeneric')}
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
