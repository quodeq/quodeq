import useProviderSettings from '../hooks/useProviderSettings.js';
import { useProviderTabsState } from '../hooks/useProviderTabsState.js';
import { classifyProvider, defaultsForProvider } from './providerUtils.js';
import OllamaTab from './OllamaTab.jsx';
import LlamaCppTab from './LlamaCppTab.jsx';
import OmlxTab from './OmlxTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';
import HelpHint from '../../../components/HelpHint.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { tRich } from '../../../strings/rich.jsx';

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

function ProviderPillRow({ clients, activeTab, selectTab }) {
  return (
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
  );
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
  const { clients, clientsError, activeTab, active, selectTab } = useProviderTabsState(providerConfigs);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.analysisLabel')}</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error">{clientsError}</span></div>}
      <ProviderPillRow clients={clients} activeTab={activeTab} selectTab={selectTab} />
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
