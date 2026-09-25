import useProviderSettings from '../hooks/useProviderSettings.js';
import { useProviderTabsState } from '../hooks/useProviderTabsState.js';
import { classifyProvider, defaultsForProvider, PROVIDER_CLASSIFICATION } from './providerUtils.js';
import { PROVIDER } from '../../../vocab/provider.js';
import OllamaTab from './OllamaTab.jsx';
import LlamaCppTab from './LlamaCppTab.jsx';
import OmlxTab from './OmlxTab.jsx';
import CliProviderTab from './CliProviderTab.jsx';
import CloudProviderTab from './CloudProviderTab.jsx';
import { ProviderPillGroup } from './ProviderPillGroup.jsx';
import { SettingsRowLabel } from './settingsRowParts.jsx';
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
  copilot: tRich('settings.installHintCopilot'),
};

function ProviderPillRow({ clients, activeTab, selectTab }) {
  return (
    <div className="settings-row">
      <SettingsRowLabel
        label={t('settings.aiProvider')}
        hint={PROVIDER_HINT}
        hintAria={t('settings.aiProviderHelpAria')}
        description={t('settings.providerRunsDesc')}
      />
      <ProviderPillGroup clients={clients} activeId={activeTab} onSelect={selectTab} selectUninstalled />
    </div>
  );
}

function TabContent({ provider, providerConfig }) {
  const classification = classifyProvider(provider.id, provider.type, providerConfig);
  const defaults = defaultsForProvider(classification, provider.id);
  const { state, update } = useProviderSettings(provider.id, defaults);

  if (classification === PROVIDER_CLASSIFICATION.LOCAL_API) {
    if (provider.id === PROVIDER.LLAMACPP) {
      return <LlamaCppTab state={state} update={update} />;
    }
    if (provider.id === PROVIDER.OMLX) {
      return <OmlxTab state={state} update={update} />;
    }
    return <OllamaTab state={state} update={update} />;
  }
  if (classification === PROVIDER_CLASSIFICATION.CLI) {
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
