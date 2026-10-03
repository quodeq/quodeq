import useAssistantProvider from '../hooks/useAssistantProvider.js';
import { useAiClientList } from '../hooks/useAiClientList.js';
import { AssistantModeRows } from './AssistantModeRows.jsx';
import { ProviderPillGroup } from './ProviderPillGroup.jsx';
import { SettingsRowLabel, SettingsEnableRow } from './settingsRowParts.jsx';
import AssistantModelPicker from './AssistantModelPicker.jsx';
import SectionLabel from '../../../components/terminal/SectionLabel.jsx';
import { t } from '../../../strings/index.js';
import { CopilotModelStatus } from './CopilotModelSelect.jsx';
import { PROVIDER } from '../../../vocab/provider.js';
import { ASSISTANT_MODE } from '../settingsVocab.js';

function AssistantCustomProviderSection({ clients, activeProvider, setActiveProvider, active, providerConfigs, model, setModel }) {
  return (
    <>
      <div className="settings-row">
        <SettingsRowLabel hintSlot={false} label={t('settings.aiProvider')} description={t('settings.assistantProviderDesc')} />
        <ProviderPillGroup clients={clients} activeId={activeProvider} onSelect={setActiveProvider} />
      </div>
      {active?.id === PROVIDER.COPILOT && <CopilotModelStatus />}
      {active && (
        <div className="settings-row settings-row--last">
          <SettingsRowLabel hintSlot={false} label={t('settings.modelLabel')} description={t('settings.assistantModelDesc')} />
          <AssistantModelPicker
            provider={active}
            providerConfig={providerConfigs?.[active.id] || {}}
            value={model}
            onChange={setModel}
          />
        </div>
      )}
    </>
  );
}

export default function AssistantProviderTabs({ providerConfigs }) {
  const { clients, clientsError } = useAiClientList(providerConfigs);
  const { enabled, setEnabled, mode, setMode, activeProvider, setActiveProvider, model, setModel } = useAssistantProvider();

  const active = clients.find((c) => c.id === activeProvider);

  return (
    <section className="panel settings-section">
      <div className="panel-header">
        <SectionLabel marker="▶">{t('settings.assistantLabel')}</SectionLabel>
      </div>
      {clientsError && <div className="settings-row"><span className="settings-error" role="alert">{clientsError}</span></div>}

      <SettingsEnableRow
        enabled={enabled}
        setEnabled={setEnabled}
        label={t('settings.assistantEnable')}
        description={t('settings.assistantEnableDesc')}
      />

      <AssistantModeRows enabled={enabled} mode={mode} setMode={setMode} active={active} activeProvider={activeProvider} model={model} />

      {enabled && mode === ASSISTANT_MODE.CUSTOM && (
        <AssistantCustomProviderSection
          clients={clients} activeProvider={activeProvider} setActiveProvider={setActiveProvider}
          active={active} providerConfigs={providerConfigs} model={model} setModel={setModel}
        />
      )}
    </section>
  );
}
