import React from 'react';
import { useAssistantDrawer } from './AssistantDrawerProvider.jsx';
import { useSidePane, workspaceDiffSpec } from '../side-pane/index.js';
import PanelSwitcher from '../drawer/PanelSwitcher.jsx';
import Badge from '../../components/Badge.jsx';
import {
  ChevronDownIcon, GlobeIcon, MaximizeIcon, MinimizeIcon, PencilIcon, RotateCcwIcon,
} from '../../components/CopyButton.jsx';
import { QMarkIcon } from '../../components/QMarkIcon.jsx';
import { providerSupportsWebTools } from '../../models/provider.js';
import { t } from '../../strings/index.js';

/**
 * The assistant panel's own header: panel switcher, animated compass
 * identity, the live model chip (click opens Settings), the session-state
 * chips, and the window controls that used to live in the shared drawer
 * header.
 */
export default function AssistantHeader({ selectedProject, onOpenSettings }) {
  const { closeActiveTab, maximized, toggleMaximized, provider, model,
          openPanels, streaming, webEnabled, toggleWebEnabled,
          writeEnabled, toggleWriteEnabled, repoInfo, workspace, refreshWorkspace,
          sessionId, sessionReady, resetConversation, readOnly } = useAssistantDrawer();
  const { addWindow } = useSidePane();

  // Chip label: "Provider · model" (provider capitalized for display, e.g.
  // "Claude · sonnet"). Falls back to whichever half is present.
  const cap = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
  const modelLabel = [cap(provider), model].filter(Boolean).join(' · ');

  return (
    <header className="assistant-panel-header">
      <PanelSwitcher />
      {/* Identity icon only while the switcher is absent (single open panel):
          with both panels open the switcher already carries the Q mark, and
          the same glyph must never appear twice in one header. */}
      {openPanels.length < 2 && (
        <span className="assistant-compass-block" aria-hidden="true">
          {streaming && <span className="assistant-think-ring" />}
          <QMarkIcon className={`assistant-compass${streaming ? ' assistant-compass--think' : ''}`} />
        </span>
      )}
      <div className="assistant-panel-identity">
        <div className="assistant-panel-title">{t('assistant.assistantLabel')}</div>
        <div className="assistant-panel-subtitle">
          {selectedProject ? t('assistant.projectSub', { name: selectedProject }) : t('assistant.noProjectSelected')}
        </div>
      </div>
      {readOnly && (
        <Badge variant="tag" tone="info" title={t('assistant.readOnlyTitle')}>
          {t('assistant.readOnly')}
        </Badge>
      )}
      {/* Repo attachment is the NORMAL case — only the exception is worth a
          chip. When the session has no repo the assistant's code-reading
          tools are dead, so surface that as a warning with the server's
          reason; stay silent when everything is fine. */}
      {repoInfo && !repoInfo.attached && (
        <Badge variant="tag" tone="warning"
          title={t('assistant.repoNotAttached', { reason: repoInfo.reason || t('assistant.unknownReason') })}>
          {t('assistant.noRepoAccess')}
        </Badge>
      )}
      {workspace?.filesChanged > 0 && (
        <button type="button" className="badge badge--tag badge--danger drawer-changes-chip"
          onClick={() => addWindow(workspaceDiffSpec({ sessionId, key: workspace.createdAt, onChanged: refreshWorkspace }))}
          title={t('assistant.reviewPendingChanges')}>
          {workspace.filesChanged === 1
            ? t('assistant.filesChangedOne', { count: workspace.filesChanged })
            : t('assistant.filesChangedMany', { count: workspace.filesChanged })}
        </button>
      )}
      <div className="assistant-drawer-controls">
        {/* Model chip leads the right-side cluster, aligned with the action
            buttons; status badges stay on the left with the identity. */}
        {modelLabel && (
          <button type="button" className="assistant-model-chip"
            title={t('assistant.modelChangeHint', { model: modelLabel })}
            onClick={() => {
              // Jump to Settings AND tuck the panel away: the drawer would
              // otherwise cover the provider section the user is heading to.
              onOpenSettings?.();
              closeActiveTab();
            }}>
            <span className="assistant-model-dot" aria-hidden="true" />
            <span className="assistant-model-name">{modelLabel}</span>
          </button>
        )}
        <button type="button" className="assistant-drawer-btn"
          onClick={resetConversation}
          aria-label={t('assistant.newConversation')}
          title={t('assistant.newConversationHint')}
          disabled={streaming || !sessionReady}>
          <RotateCcwIcon />
        </button>
        {repoInfo?.writeAvailable && (
          <button type="button" className="assistant-drawer-btn assistant-drawer-write"
            onClick={toggleWriteEnabled}
            aria-pressed={writeEnabled}
            aria-label={t('assistant.allowRepoEdits')}
            title={t('assistant.allowRepoEditsHint')}
            disabled={streaming}>
            <PencilIcon />
          </button>
        )}
        {providerSupportsWebTools(provider) && (
          <button type="button" className="assistant-drawer-btn assistant-drawer-web"
            onClick={toggleWebEnabled}
            aria-pressed={webEnabled}
            aria-label={t('assistant.allowWebAccess')}
            title={t('assistant.allowWebAccess')}
            disabled={streaming}>
            <GlobeIcon />
          </button>
        )}
        <button type="button" className="assistant-drawer-btn" onClick={toggleMaximized}
          aria-label={maximized ? t('common.restoreDrawer') : t('common.maximizeDrawer')}
          aria-pressed={maximized}
          title={maximized ? 'Restore' : 'Maximize'}>
          {maximized ? <MinimizeIcon /> : <MaximizeIcon />}
        </button>
        {/* Chevron-down, NOT an ×: neither panel is killed by this. An
            in-flight assistant turn keeps running server-side; reopening the
            tab reattaches to it. */}
        <button type="button" className="assistant-drawer-btn" onClick={closeActiveTab}
          aria-label={t('common.hideTab')} title={t('common.hideKeepsRunning')}>
          <ChevronDownIcon />
        </button>
      </div>
    </header>
  );
}
